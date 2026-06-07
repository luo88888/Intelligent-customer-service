"""
对话记忆管理器（ConversationMemory）

管理长时间对话的记忆，在对话内容超过阈值时自动调用 LLM 进行增量摘要。
同时保留完整对话历史，方便按需获取摘要和最近对话。

配置项（config/agent.yaml → memory 节）：
    - threshold: 未摘要消息总字符数超过此阈值时触发摘要（默认 1000）
    - keep_recent_count: 摘要时保留最近多少条消息不参与摘要（默认 6）
    - recent_context_count: get_context() 返回的最近未摘要消息数量（默认 10）
    - summary_prompt_path: 摘要提示词文件路径（为空则使用默认提示词）
    - llm_provider: 用于摘要的 LLM 提供商（默认 deepseek）
    - llm_model: 用于摘要的 LLM 模型名（默认 deepseek-v4-flash）
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, PrivateAttr

from utils.config_handler import memory_conf
from utils.path_tool import get_abs_path
from model.factory import create_chat_model

DEFAULT_SUMMARY_PROMPT = """\
请对以下对话历史进行简洁摘要，保留关键信息，用中文输出，不超过 1000 字。

=== 已有摘要 ===
{existing_summary}


=== 对话历史 ===
{conversation_text}


请生成更新后的完整摘要，只输出摘要即可，不要输出其它信息："""


class ConversationMemory(BaseModel):
    """对话记忆管理器

    自动管理长对话的记忆，当未摘要的对话内容超过指定字符阈值时，
    自动调用 LLM 对较早的对话进行摘要，同时保留最近对话的完整内容。

    Attributes:
        messages: 完整的对话历史列表
        summary_text: 累积摘要文本
        summarized_count: 已摘要的消息数量
    """

    messages: List[Dict[str, str]] = []
    summary_text: str = ""
    summarized_count: int = 0
    
    _threshold: int = PrivateAttr(default=1000)
    _keep_recent_count: int = PrivateAttr(default=6)
    _summary_prompt: str = PrivateAttr(default=DEFAULT_SUMMARY_PROMPT)
    _llm: Any = PrivateAttr(default=None)

    def __init__(self, **data: Any):
        super().__init__(**data)
        # 从配置文件读取记忆模块参数（config/agent.yaml → memory 节）
        self._threshold = memory_conf.get("threshold", 1000)
        self._keep_recent_count = memory_conf.get("keep_recent_count", 6)
        self._recent_context_count = memory_conf.get("recent_context_count", 10)

        # 加载摘要提示词（优先使用配置文件指定的路径，否则使用默认提示词）
        summary_prompt_path = memory_conf.get("summary_prompt_path", "")
        if summary_prompt_path:
            try:
                abs_path = get_abs_path(summary_prompt_path)
                with open(abs_path, "r", encoding="utf-8") as f:
                    self._summary_prompt = f.read()
            except Exception:
                self._summary_prompt = DEFAULT_SUMMARY_PROMPT
        else:
            self._summary_prompt = DEFAULT_SUMMARY_PROMPT

        # 创建用于摘要的 LLM
        llm_provider = memory_conf.get("llm_provider", "deepseek")
        llm_model_name = memory_conf.get("llm_model", "deepseek-v4-flash")
        self._llm = create_chat_model(provider=llm_provider, model_name=llm_model_name)

    @property
    def summary(self) -> str:
        """获取当前的累积摘要文本"""
        return self.summary_text

    @property
    def message_count(self) -> int:
        """获取完整对话历史中的消息总数"""
        return len(self.messages)

    def add_message(
        self,
        role: str,
        content: str,
        created_at: Optional[str] = None,
    ) -> None:
        """添加一条消息，并自动检查是否需要触发摘要

        添加消息后会自动检测未摘要消息的总字符数。若超过阈值，
        则对较早消息（保留最近 keep_recent_count 条）进行增量摘要。

        Args:
            role: 消息角色，如 "user" 或 "assistant"
            content: 消息文本内容
            created_at: 消息创建时间（ISO 格式字符串），为 None 时自动填充当前 UTC 时间
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        self.messages.append({
            "role": role,
            "content": content,
            "created_at": created_at,
        })

        if self._should_summarize():
            self._summarize()

    def add_messages(self, messages: List[Dict[str, str]]) -> None:
        """批量添加消息，完成后检查是否需要摘要

        Args:
            messages: 消息列表，每条消息为包含 role、content 的字典，
                可选 created_at 字段
        """
        for msg in messages:
            self.add_message(
                role=msg["role"],
                content=msg["content"],
                created_at=msg.get("created_at"),
            )

    def get_context(self, recent_count: Optional[int] = None, include_latest: bool = True) -> str:
        """获取适合传递给 LLM 的上下文文本

        将摘要（如有）和最近未摘要的对话拼接在一起，
        形成可直接放入 LLM prompt 的上下文片段。

        Args:
            recent_count: 控制最近对话记录（未进行总结的）使用多少条。如果不指定，则使用配置中的 recent_count 或全部未摘要记录。
            include_latest: 是否包含最新的一条对话记录，默认为 True。
            
        Returns:
            格式化的上下文字符串。如果无摘要且无消息，返回提示文本。
        """
        if recent_count is None:
            recent_count = self._recent_context_count
            
        parts: List[str] = []

        if self.summary_text:
            parts.append(f"=== 历史对话摘要 ===\n{self.summary_text}")

        unsummarized = self.messages[self.summarized_count:]
        
        if not include_latest and unsummarized:
            unsummarized = unsummarized[:-1]
            
        if recent_count > 0:
            unsummarized = unsummarized[-recent_count:]

        if unsummarized:
            recent_text = self._format_messages(unsummarized)
            parts.append(f"=== 最近对话记录 ===\n{recent_text}")

        if not parts:
            return "（暂无对话记录）"

        return "\n\n".join(parts)

    def get_recent_messages(self) -> List[Dict[str, str]]:
        """获取尚未被摘要的最近消息

        Returns:
            未摘要的消息列表（按时间顺序）
        """
        return list(self.messages[self.summarized_count:])

    def get_full_history(self) -> List[Dict[str, str]]:
        """获取完整的原始对话历史

        Returns:
            完整消息列表的副本（按时间顺序）
        """
        return list(self.messages)

    def get_summary_and_recent(self) -> tuple:
        """同时获取摘要文本和最近未摘要消息列表

        Returns:
            (summary, recent_messages) 元组
        """
        return (self.summary_text, self.get_recent_messages())

    def _should_summarize(self) -> bool:
        """判断当前是否需要对未摘要消息进行摘要

        当未摘要消息的总字符数超过阈值时返回 True。

        Returns:
            是否需要触发摘要
        """
        unsummarized = self.messages[self.summarized_count:]
        total_chars = sum(len(msg["content"]) for msg in unsummarized)
        return total_chars > self._threshold

    def _summarize(self) -> None:
        """对较早的未摘要消息进行增量摘要

        处理逻辑：
            1. 从未摘要消息中分离出"待摘要部分"和"保留部分"
               （保留最近 keep_recent_count 条不动）
            2. 将待摘要部分格式化为文本
            3. 调用 LLM，结合已有摘要生成更新后的摘要
            4. 更新 _summary 和 _summarized_count

        如果 LLM 调用失败，不更新摘要状态，避免丢失数据。
        """
        unsummarized = self.messages[self.summarized_count:]
        if len(unsummarized) <= self._keep_recent_count:
            return

        to_summarize = unsummarized[: -self._keep_recent_count]
        conversation_text = self._format_messages(to_summarize)
        existing_summary = self.summary_text or "（无）"

        prompt_text = self._summary_prompt.format(
            conversation_text=conversation_text,
            existing_summary=existing_summary,
        )

        try:
            from langchain_core.messages import HumanMessage
            response = self._llm.invoke([HumanMessage(content=prompt_text)])
            new_summary = response.content.strip() if hasattr(response, "content") else str(response).strip()
        except Exception:
            return

        self.summary_text = new_summary
        self.summarized_count += len(to_summarize)

    @staticmethod
    def _format_messages(messages: List[Dict[str, str]]) -> str:
        """将消息列表格式化为可读的文本

        Args:
            messages: 消息字典列表

        Returns:
            格式化的多行文本，每行格式为 "[角色标签] 内容"
        """
        lines: List[str] = []
        for msg in messages:
            role_label = "用户" if msg["role"] == "user" else "客服"
            lines.append(f"[{role_label}] {msg['content']}")
        return "\n".join(lines)
