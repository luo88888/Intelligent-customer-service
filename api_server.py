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
import dotenv
dotenv.load_dotenv(override=True)

import uuid
import time
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, status as http_status
from fastapi.responses import JSONResponse, StreamingResponse
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
from utils.token_budget import TokenBudgetExceededError, check_budget_or_raise


# ====== 应用生命周期 ======

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库表，关闭前持久化 token 用量"""
    init_db()
    yield
    # 应用关闭前，将 token 用量写入文件
    from utils.token_budget import force_save
    force_save()


app = FastAPI(title="智扫通 Agent API", lifespan=lifespan)

# CORS 中间件：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 全局异常处理器 ======

@app.exception_handler(TokenBudgetExceededError)
async def token_budget_exceeded_handler(request, exc: TokenBudgetExceededError):
    """Token 预算超限异常 → HTTP 429 响应"""
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": "token_budget_exceeded",
            "message": exc.message,
            "reject_message": exc.message,  # 前端用于展示的拒绝信息
            "detail": exc.message,          # 兼容前端 ApiError 的 detail 字段
            "usage": exc.usage,
        },
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
    # 全局 token 预算检查
    check_budget_or_raise()

    memory, user_query = _build_memory_from_messages(request.messages)
    agent = ReactAgent(memory=memory)

    # 将同步的 Agent 执行放到线程池中，避免阻塞事件循环
    def _run_agent():
        chunks = []
        for chunk in agent.execute_stream(user_query):
            chunks.append(chunk)
        return chunks

    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, _run_agent)

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
    # 全局 token 预算检查
    check_budget_or_raise()

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
    """处理流式消息：以 SSE 格式逐块返回 Agent 输出

    将同步的 Agent 生成器放到线程池中执行，通过 queue.Queue 将 chunk
    传递回事件循环线程，确保 LLM 调用的同步 I/O 不会阻塞事件循环，
    从而实现多用户并发处理。
    """
    import queue as sync_queue
    from functools import partial

    chat_svc = ChatService(db)

    def _format_sse_payload(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        # 线程安全队列：同步 Agent 在子线程中将 chunk 放入，
        # 事件循环线程通过 run_in_executor 轮询取出，每次 await 都会让出控制权
        chunk_queue: sync_queue.Queue = sync_queue.Queue()

        def run_sync():
            """在子线程中运行同步 Agent 生成器，将结果写入队列"""
            try:
                for chunk in chat_svc.execute_and_persist_stream(conversation_id, content):
                    chunk_queue.put(("chunk", chunk))
                chunk_queue.put(("done", None))
            except Exception as e:
                chunk_queue.put(("error", e))

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run_sync)

        try:
            while True:
                # 在线程池中阻塞等待队列数据（timeout=0.05s），
                # await 使每次轮询都让出事件循环，不会阻塞其他请求
                try:
                    tag, value = await loop.run_in_executor(
                        None, partial(chunk_queue.get, timeout=0.05)
                    )
                except sync_queue.Empty:
                    await asyncio.sleep(0)
                    continue

                if tag == "done":
                    break

                if tag == "error":
                    # 子线程中未预见的异常（execute_and_persist_stream 内部
                    # 可预见的错误已通过 error 类型 chunk 产出）
                    error_data = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": "smart-sweep-agent",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "error": {
                                    "type": "server_error",
                                    "message": str(value),
                                    "reject_message": "服务暂时不可用，请稍后重试",
                                }
                            },
                            "finish_reason": "error",
                        }],
                    }
                    yield _format_sse_payload(error_data)
                    await asyncio.sleep(0)
                    return

                # tag == "chunk": 正常处理 Agent 产出的 chunk
                chunk = value

                if isinstance(chunk, dict) and chunk.get("type") == "text":
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

                elif isinstance(chunk, dict) and chunk.get("type") == "error":
                    # Agent 内部产出的错误 chunk（如 token 预算超限），透传
                    error_data = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": "smart-sweep-agent",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "error": {
                                    "type": chunk.get("error", "agent_error"),
                                    "message": chunk.get("message", ""),
                                    "reject_message": chunk.get("reject_message", ""),
                                }
                            },
                            "finish_reason": "error",
                        }],
                    }
                    yield _format_sse_payload(error_data)
                    await asyncio.sleep(0)
                    return

        except Exception as e:
            # 兜底：队列通信或 SSE 写入本身的异常
            error_data = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": "smart-sweep-agent",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "error": {
                            "type": "server_error",
                            "message": str(e),
                            "reject_message": "服务暂时不可用，请稍后重试",
                        }
                    },
                    "finish_reason": "error",
                }],
            }
            try:
                yield _format_sse_payload(error_data)
            except Exception:
                pass

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


# ====== 管理接口 ======

@app.get("/api/admin/token-usage")
def get_token_usage():
    """查询当前全局 token 使用统计"""
    from utils.token_budget import get_tracker
    return get_tracker().get_usage()


@app.post("/api/admin/token-usage/reset")
def reset_token_usage():
    """重置全局 token 计数器为零"""
    from utils.token_budget import get_tracker
    get_tracker().reset()
    return {"status": "ok", "message": "Token budget counter has been reset."}


@app.post("/api/admin/token-usage/save")
def force_save_token_usage():
    """强制将 token 用量立即写入持久化文件"""
    from utils.token_budget import get_tracker
    get_tracker().force_save()
    return {"status": "ok", "message": "Token usage has been saved to file."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
