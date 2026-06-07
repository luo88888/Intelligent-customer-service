"""
聊天业务逻辑层

编排 Agent 执行与数据库持久化，将 ReactAgent 与 ConversationMemory
的运行时状态同步到 MySQL。
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agent.react_agent import ReactAgent
from agent.ConversationMemory import ConversationMemory
from db.models.conversation import Conversation
from db.models.message import Message
from db.repository.conversation_repo import ConversationRepository
from db.repository.message_repo import MessageRepository


class ChatService:
    """聊天服务：编排 Agent 执行与消息持久化"""

    def __init__(self, db: Session):
        self.db = db
        self.conv_repo = ConversationRepository(db)
        self.msg_repo = MessageRepository(db)

    def load_conversation_memory(self, conversation_id: int) -> tuple[Conversation, ConversationMemory]:
        """从数据库加载会话，重建 ConversationMemory

        Args:
            conversation_id: 会话 ID

        Returns:
            (Conversation ORM, 重建的 ConversationMemory) 元组

        Raises:
            ValueError: 会话不存在
        """
        conv = self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise ValueError("会话不存在")

        messages = self.msg_repo.list_by_conversation(conversation_id)

        memory = ConversationMemory(
            messages=[
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    if m.created_at else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                }
                for m in messages
            ],
            summary_text=conv.summary_text or "",
            summarized_count=conv.summarized_count or 0,
        )
        return conv, memory

    def persist_state(self, conversation_id: int, memory: ConversationMemory) -> None:
        """将 ConversationMemory 的当前状态写回数据库

        包括累积摘要文本和已摘要消息计数。首次发送消息时自动设置会话标题。

        Args:
            conversation_id: 会话 ID
            memory: 当前的 ConversationMemory 实例
        """
        self.conv_repo.update_summary(
            conversation_id,
            memory.summary_text,
            memory.summarized_count,
        )

        # 自动设置标题：取第一条用户消息的前 30 个字符
        conv = self.conv_repo.get_by_id(conversation_id)
        if conv and not conv.title and memory.messages:
            first_user_msg = next(
                (m["content"] for m in memory.messages if m["role"] == "user"),
                None
            )
            if first_user_msg:
                title = first_user_msg[:30] + ("..." if len(first_user_msg) > 30 else "")
                self.conv_repo.update_title(conversation_id, title)

    def save_user_message(self, conversation_id: int, content: str) -> Message:
        """持久化用户消息到数据库

        Args:
            conversation_id: 会话 ID
            content: 消息文本

        Returns:
            新创建的 Message ORM 对象
        """
        return self.msg_repo.create(conversation_id, "user", content)

    def save_assistant_message(self, conversation_id: int, content: str,
                               blocks: list[dict] | None = None) -> Message:
        """持久化助手消息到数据库

        Args:
            conversation_id: 会话 ID
            content: 消息文本（最终回复文本）
            blocks: 中间块列表（思考过程、工具调用、检索文档等）

        Returns:
            新创建的 Message ORM 对象
        """
        return self.msg_repo.create(conversation_id, "assistant", content, blocks)

    @staticmethod
    def _normalize_blocks(chunks: list[dict]) -> list[dict]:
        """将 Agent 产生的原始 chunk 列表转换为前端 StreamBlock 格式

        Agent 产出格式（snake_case）：
          {type: "text", subtype: "thinking"|"tool_result"|"answer", content, tool_calls?, tool_name?}
          {type: "rag_docs", query, docs}

        前端期望格式（camelCase）：
          {id, type: "thinking"|"tool_result"|"answer"|"rag_docs", content, toolCalls?, toolName?, query?, docs?}

        Args:
            chunks: ReactAgent.execute_stream() 产生的原始 chunk 列表

        Returns:
            规范化后的 block 列表
        """
        blocks: list[dict] = []
        for i, chunk in enumerate(chunks):
            block: dict = {"id": f"block_{i + 1}"}
            if chunk.get("type") == "text":
                block["type"] = chunk.get("subtype", "answer")
                block["content"] = chunk.get("content", "")
                if "tool_calls" in chunk:
                    block["toolCalls"] = chunk["tool_calls"]
                if "tool_name" in chunk:
                    block["toolName"] = chunk["tool_name"]
            elif chunk.get("type") == "rag_docs":
                block["type"] = "rag_docs"
                block["content"] = ""
                block["query"] = chunk.get("query", "")
                block["docs"] = chunk.get("docs", [])
            blocks.append(block)
        return blocks

    def execute_and_persist(self, conversation_id: int, user_content: str) -> dict:
        """核心流程：发送消息 → 运行 Agent → 持久化 → 返回结果

        流程：
        1. 从数据库加载会话历史，重建 ConversationMemory
        2. 持久化用户消息到 DB
        3. 创建 ReactAgent（注入已有 memory）
        4. 调用 agent.execute_stream() 收集回复
        5. 将 ConversationMemory 的最新状态写回数据库
        6. 持久化助手消息到 DB（包含中间块）
        7. 返回结果给客户端

        Args:
            conversation_id: 会话 ID
            user_content: 用户发送的消息文本

        Returns:
            包含 message_id, role, content, blocks, rag_docs, created_at 的字典

        Raises:
            ValueError: 会话不存在
            TokenBudgetExceededError: 全局 token 预算超限
        """
        from utils.token_budget import TokenBudgetExceededError

        conv, memory = self.load_conversation_memory(conversation_id)

        # 持久化用户消息
        self.save_user_message(conversation_id, user_content)

        # 将用户消息添加到 memory（execute_stream 的防重复守卫会跳过重复添加）
        memory.add_message(role="user", content=user_content)

        # 创建 Agent 并注入已有记忆
        agent = ReactAgent(memory=memory)

        # 收集 Agent 输出的所有 chunk
        all_chunks: list[dict] = []
        final_text = ""
        rag_docs = []
        try:
            for chunk in agent.execute_stream(user_content):
                all_chunks.append(chunk)
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    final_text += chunk["content"]
                elif isinstance(chunk, dict) and chunk.get("type") == "rag_docs":
                    rag_docs.append(chunk)
        except Exception as e:
            # 检查是否为上游 LLM 的 token/rate-limit 错误（如 DeepSeek 429）
            error_msg = str(e)
            if "429" in error_msg or "rate" in error_msg.lower() or "token" in error_msg.lower():
                raise TokenBudgetExceededError(
                    config=__import__('utils.token_budget').token_budget.get_tracker().config,
                    total_tokens=__import__('utils.token_budget').token_budget.get_tracker().get_usage()["total_tokens"],
                ) from e
            raise

        # 将 memory 的最新状态同步到数据库
        self.persist_state(conversation_id, memory)

        # 规范化中间块并持久化助手消息
        blocks = self._normalize_blocks(all_chunks)
        assistant_msg = self.save_assistant_message(
            conversation_id, final_text, blocks if blocks else None
        )

        return {
            "message_id": assistant_msg.id,
            "role": "assistant",
            "content": final_text,
            "blocks": blocks if blocks else None,
            "rag_docs": rag_docs if rag_docs else None,
            "created_at": assistant_msg.created_at,
        }

    def execute_and_persist_stream(self, conversation_id: int, user_content: str):
        """流式版本：发送消息 → 运行 Agent → 持久化 → 逐块产出

        与 execute_and_persist 逻辑相同，但以生成器方式逐块返回 Agent 输出，
        适用于 SSE 流式响应场景。流结束后将中间块一并持久化。

        若 Agent 执行过程中发生 token/rate-limit 错误，会先 yield error 类型的
        chunk 再抛出异常，确保前端能通过 SSE 收到错误信息。

        Args:
            conversation_id: 会话 ID
            user_content: 用户发送的消息文本

        Yields:
            dict: 包含 type 和 content 的分块字典
        """
        from utils.token_budget import TokenBudgetExceededError

        conv, memory = self.load_conversation_memory(conversation_id)

        # 持久化用户消息
        self.save_user_message(conversation_id, user_content)

        # 将用户消息添加到 memory
        memory.add_message(role="user", content=user_content)

        # 创建 Agent 并注入已有记忆
        agent = ReactAgent(memory=memory)

        # 流式收集并产出
        all_chunks: list[dict] = []
        final_text = ""
        try:
            for chunk in agent.execute_stream(user_content):
                yield chunk
                all_chunks.append(chunk)
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    final_text += chunk["content"]
        except Exception as e:
            # 检查是否为上游 LLM 的 token/rate-limit 错误（如 DeepSeek 429）
            error_msg = str(e)
            if "429" in error_msg or "rate" in error_msg.lower() or "token" in error_msg.lower():
                tracker = __import__('utils.token_budget').token_budget.get_tracker()
                budget_error = TokenBudgetExceededError(
                    config=tracker.config,
                    total_tokens=tracker.get_usage()["total_tokens"],
                )
                yield {
                    "type": "error",
                    "error": "token_budget_exceeded",
                    "message": budget_error.message,
                    "reject_message": budget_error.message,
                }
                raise budget_error from e
            else:
                yield {
                    "type": "error",
                    "error": "agent_error",
                    "message": f"Agent 执行错误: {error_msg}",
                    "reject_message": f"服务暂时不可用，请稍后重试: {error_msg[:100]}",
                }
                raise

        # 将 memory 的最新状态同步到数据库
        self.persist_state(conversation_id, memory)

        # 规范化中间块并持久化助手消息
        blocks = self._normalize_blocks(all_chunks)
        self.save_assistant_message(
            conversation_id, final_text, blocks if blocks else None
        )
