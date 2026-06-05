"""
智扫通 Agent API 服务

提供以下接口：
- POST /v1/chat/completions       OpenAI 兼容接口（兼容 Open WebUI）
- POST /api/auth/register         用户注册
- POST /api/auth/login            用户登录
- GET  /api/conversations          获取会话列表
- POST /api/conversations          创建新会话
- GET  /api/conversations/{id}     获取会话详情
- DELETE /api/conversations/{id}   删除会话
- GET  /api/conversations/{id}/messages       获取会话全部消息
- POST /api/conversations/{id}/messages       发送消息（非流式）
- POST /api/conversations/{id}/messages?stream=true  发送消息（SSE 流式）
2. 只杀占用 8000 端口的进程（精准）

netstat -ano | findstr :8000
# 记下最后一列的 PID，然后：
taskkill //F //PID <PID>
"""
import uuid
import time
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, status as http_status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from db.connection import get_db, init_db
from db.models.user import User
from auth.dependencies import get_current_user
from schemas.auth_schemas import RegisterRequest, LoginRequest, TokenResponse
from schemas.conversation_schemas import (
    ConversationListResponse,
    ConversationDetailResponse,
    CreateConversationRequest,
)
from schemas.message_schemas import (
    MessageListResponse,
    MessageSendRequest,
    MessageSendResponse,
)
from services.auth_service import AuthService
from services.conversation_service import ConversationService
from services.chat_service import ChatService
from agent.react_agent import ReactAgent
from agent.ConversationMemory import ConversationMemory


# ====== 应用生命周期 ======

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库表"""
    init_db()
    yield


app = FastAPI(title="智扫通 Agent API", lifespan=lifespan)

# CORS 中间件：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== OpenAI 兼容接口（Open WebUI） ======

class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: Optional[bool] = False


def _build_memory_from_messages(messages: List[Message]) -> tuple[ConversationMemory, str]:
    """将 OpenAI 格式的 messages 列表转换为 ConversationMemory

    解析客户端传来的完整对话历史，填充到 ConversationMemory 中，
    使 Agent 能够感知多轮对话上下文。最后一条 user 消息作为当前 query。

    Args:
        messages: OpenAI 格式的消息列表，按时间升序

    Returns:
        (ConversationMemory, query) 元组
            - memory: 填充了历史消息的对话记忆（不含最后一条 user 消息）
            - query: 最后一条 user 消息内容
    """
    # 提取最后一条 user 消息作为当前 query
    query = ""
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            query = messages[i].content
            last_user_idx = i
            break

    if not query:
        query = messages[-1].content  # 兜底

    # 将历史消息（不含最后一条 user 消息）填充到 memory
    # 因为 execute_stream 会自动添加当前 user 消息和 assistant 回复
    memory = ConversationMemory()
    for i, msg in enumerate(messages):
        if msg.role == "system":
            continue  # system 消息不存入记忆，避免污染对话摘要
        if i == last_user_idx:
            break  # 不预填最后一条 user 消息，交给 execute_stream 处理
        memory.add_message(role=msg.role, content=msg.content)

    return memory, query


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI 兼容接口，用于 Open WebUI 等第三方前端接入

    改进的上下文处理：
    - 解析完整的 messages 列表 → ConversationMemory，实现多轮对话上下文感知
    - 每次请求创建独立的 ReactAgent 实例，杜绝多用户上下文污染
    """
    memory, user_query = _build_memory_from_messages(request.messages)
    agent = ReactAgent(memory=memory)

    chunks = []
    for chunk in agent.execute_stream(user_query):
        chunks.append(chunk)

    text_chunks = [
        c["content"] for c in chunks
        if isinstance(c, dict) and c.get("type") == "text"
    ]
    rag_docs = [
        c for c in chunks
        if isinstance(c, dict) and c.get("type") == "rag_docs"
    ]

    final_response = "".join(text_chunks) if text_chunks else "抱歉，没有得到有效的回复。"

    if request.stream:
        async def event_stream():
            chat_id = f"chatcmpl-{uuid.uuid4().hex}"
            created_time = int(time.time())

            for char in final_response:
                data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"content": char}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if rag_docs:
                docs_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"rag_docs": rag_docs},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(docs_data, ensure_ascii=False)}\n\n"

            final_data = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": request.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            }
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": final_response},
            "finish_reason": "stop"
        }],
        "rag_docs": rag_docs if rag_docs else None,
    }


# ====== 认证接口 ======

@app.post("/api/auth/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    auth_svc = AuthService(db)
    return auth_svc.register(req.username, req.password, req.display_name)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    auth_svc = AuthService(db)
    return auth_svc.login(req.username, req.password)


# ====== 会话接口 ======

@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的会话列表（分页，按更新时间降序）"""
    svc = ConversationService(db)
    return svc.list_conversations(current_user.id, page, page_size)


@app.post("/api/conversations", response_model=ConversationDetailResponse, status_code=201)
def create_conversation(
    req: CreateConversationRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新会话"""
    svc = ConversationService(db)
    title = req.title if req else None
    return svc.create_conversation(current_user.id, title)


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取会话详情"""
    svc = ConversationService(db)
    return svc.get_conversation(conversation_id, current_user.id)


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除会话"""
    svc = ConversationService(db)
    svc.delete_conversation(conversation_id, current_user.id)


# ====== 消息接口 ======

@app.get("/api/conversations/{conversation_id}/messages", response_model=MessageListResponse)
def get_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取会话的全部消息（按时间升序）"""
    svc = ConversationService(db)
    return svc.get_messages(conversation_id, current_user.id)


@app.post("/api/conversations/{conversation_id}/messages", response_model=MessageSendResponse)
def send_message(
    conversation_id: int,
    req: MessageSendRequest,
    stream: bool = Query(False, description="是否流式返回"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送消息并获取 Agent 回复

    - stream=false: 返回完整的 MessageSendResponse JSON
    - stream=true: 返回 SSE (text/event-stream) 流式响应
    """
    # 校验会话归属
    conv_svc = ConversationService(db)
    conv_svc.get_conversation(conversation_id, current_user.id)

    if stream:
        return _handle_stream_message(conversation_id, req.content, db)
    else:
        return _handle_non_stream_message(conversation_id, req.content, db)


def _handle_non_stream_message(conversation_id: int, content: str, db: Session) -> MessageSendResponse:
    """处理非流式消息：运行 Agent 并返回完整结果"""
    chat_svc = ChatService(db)
    result = chat_svc.execute_and_persist(conversation_id, content)
    return MessageSendResponse(
        message_id=result["message_id"],
        role=result["role"],
        content=result["content"],
        blocks=result.get("blocks"),
        rag_docs=result.get("rag_docs"),
        created_at=result["created_at"],
    )


def _handle_stream_message(conversation_id: int, content: str, db: Session):
    """处理流式消息：以 SSE 格式逐块返回 Agent 输出"""
    chat_svc = ChatService(db)

    def _format_sse_payload(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        for chunk in chat_svc.execute_and_persist_stream(conversation_id, content):
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                # 构建 delta，携带 subtype 及可能的 tool_calls/tool_name
                delta: dict = {
                    "content": chunk["content"],
                    "subtype": chunk.get("subtype", "answer"),
                }
                if "tool_calls" in chunk:
                    delta["tool_calls"] = chunk["tool_calls"]
                if "tool_name" in chunk:
                    delta["tool_name"] = chunk["tool_name"]

                data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": "smart-sweep-agent",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }
                yield _format_sse_payload(data)
                await asyncio.sleep(0)

            elif isinstance(chunk, dict) and chunk.get("type") == "rag_docs":
                # 透传 query 和 docs 字段
                docs_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": "smart-sweep-agent",
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "rag_docs": {
                                "query": chunk.get("query", ""),
                                "docs": chunk.get("docs", []),
                            }
                        },
                        "finish_reason": None,
                    }],
                }
                yield _format_sse_payload(docs_data)
                await asyncio.sleep(0)

        # 发送结束标志
        final_data = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": "smart-sweep-agent",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield _format_sse_payload(final_data)
        await asyncio.sleep(0)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
