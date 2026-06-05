from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


from model.factory import chat_model
from utils.prompt_loader import load_system_prompt
from agent.tools.agent_tools import (
    rag_summarize,
    get_weather,
    get_user_city,
    get_user_id,
    get_current_month,
    fetch_external_data,
    fill_context_for_report,
    drain_rag_results,
    _rag_results_ctx,
)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch
from agent.ConversationMemory import ConversationMemory


class ReactAgent:
    def __init__(self, memory: ConversationMemory | None = None):
        """初始化 ReactAgent

        Args:
            memory: 可选的 ConversationMemory 实例。传入已有记忆可恢复历史对话状态；
                    为 None 时创建空记忆（适用于新会话）。
        """
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompt(),
            tools=[
                rag_summarize,
                get_weather,
                get_user_city,
                get_user_id,
                get_current_month,
                fetch_external_data,
                fill_context_for_report
            ],
            middleware=[
                monitor_tool,
                log_before_model,
                report_prompt_switch
            ]
        )
        # 初始化对话记忆管理器，用于长对话的自动摘要
        self.memory = memory or ConversationMemory()

    @staticmethod
    def _get_text(msg) -> str:
        """安全地从 LangChain 消息中提取纯文本内容

        LangChain 消息的 content 可能是 str 或 list[dict]（多模态），
        这里统一转换为纯文本字符串。
        """
        content = msg.content or ""
        if isinstance(content, str):
            return content
        # 多模态内容块：提取所有 text 类型块
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "".join(parts)
        return str(content)

    def _build_chunk(
        self,
        msg,
        subtype: str,
        extra: dict | None = None,
    ) -> dict:
        """将一条 LangChain 消息转换为统一的 chunk 字典

        Args:
            msg: LangChain 消息对象
            subtype: 消息子类型 —— "thinking" / "tool_result" / "answer"
            extra: 额外的展示字段（如 tool_name、tool_calls）

        Returns:
            {"type": "text", "subtype": ..., "content": ..., ...extra}
        """
        text = self._get_text(msg).strip()
        result: dict = {
            "type": "text",
            "subtype": subtype,
            "content": text + "\n" if text else "",
        }
        if extra:
            result.update(extra)
        return result

    def execute_stream(self, query: str):
        # 初始化当前执行上下文的 RAG 缓存（ContextVar 确保多用户并发隔离）
        _rag_results_ctx.set([])

        # 从记忆中获取上下文（含历史摘要 + 最近对话），拼接到用户问题中
        memory_context = self.memory.get_context()
        if memory_context and memory_context != "（暂无对话记录）":
            augmented_query = f"{memory_context}\n\n=== 当前用户问题 ===\n{query}"
        else:
            augmented_query = query

        input_dict = {
            "messages": [
                {"role": "user", "content": augmented_query}
            ]
        }

        # 将用户原始消息存入记忆（只存原始 query，不存含记忆上下文的 augmented_query）
        # 防重复：若 memory 中最后一条消息已经是同一 query，跳过不重复添加
        last_msg = self.memory.messages[-1] if self.memory.messages else None
        if last_msg is None or last_msg["role"] != "user" or last_msg["content"] != query:
            self.memory.add_message(role="user", content=query)

        # 追踪最终 AI 回复内容（不含 tool_calls 的纯文本回复），用于存入记忆
        final_ai_content = ""

        # 追踪上一次 chunk 的消息数量，用于计算本步新增了哪些消息
        prev_msg_count = 0

        response = self.agent.stream(input_dict, stream_mode="values", context={"report": False})
        for chunk in response:
            # 每次 agent 步进后，先排出该步中 rag_summarize 工具积累的检索文档
            for rag_entry in drain_rag_results():
                yield {"type": "rag_docs", "docs": rag_entry["docs"], "query": rag_entry["query"]}

            # 计算本步新增的消息（不只看最后一条，防止并行工具调用遗漏）
            all_messages = chunk["messages"]
            new_messages = all_messages[prev_msg_count:]
            prev_msg_count = len(all_messages)

            for msg in new_messages:
                if isinstance(msg, HumanMessage):
                    continue  # 不暴露用户消息到前端

                if isinstance(msg, ToolMessage):
                    # 工具返回结果：携带工具名，方便前端区分展示
                    yield self._build_chunk(
                        msg,
                        subtype="tool_result",
                        extra={"tool_name": msg.name},
                    )

                elif isinstance(msg, AIMessage):
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls:
                        # 思考过程：携带 tool_calls 让前端知道 Agent 打算调用哪些工具
                        yield self._build_chunk(
                            msg,
                            subtype="thinking",
                            extra={
                                "tool_calls": [
                                    {"name": tc["name"], "args": tc["args"]}
                                    for tc in tool_calls
                                ]
                            },
                        )
                    else:
                        # 最终回复
                        text = self._get_text(msg).strip()
                        if text:
                            yield self._build_chunk(msg, subtype="answer")
                            final_ai_content = text

        # 循环结束后再次 drain，防止最后一步的 RAG 文档遗漏
        for rag_entry in drain_rag_results():
            yield {"type": "rag_docs", "docs": rag_entry["docs"], "query": rag_entry["query"]}

        # 将助手最终回复存入记忆（仅存最终回复，不含思考过程和工具结果）
        if final_ai_content:
            self.memory.add_message(role="assistant", content=final_ai_content)



# python -m agent.react_agent
if __name__ == "__main__":
    query = "生成我这个月的使用报告。"
    agent = ReactAgent()
    for chunk in agent.execute_stream(query):
        if isinstance(chunk, dict) and chunk.get("type") == "text":
            print(chunk["content"], end="")
        elif isinstance(chunk, dict) and chunk.get("type") == "rag_docs":
            print(f"\n[参考资料] 查询: {chunk['query']}，共 {len(chunk['docs'])} 篇文档")
            for i, doc in enumerate(chunk["docs"], 1):
                print(f"  [{i}] {doc[:100]}...")
        else:
            print(chunk, end="")
