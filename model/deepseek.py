"""DeepSeek 模型提供商

对话模型通过 langchain_deepseek.ChatDeepSeek 创建。
嵌入模型 DeepSeek 暂不支持。

所需环境变量: DEEPSEEK_API_KEY
"""
import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings


def create_chat_model(
    model_name: str = "deepseek-v4-flash",
    temperature: float = 0.0,
    **kwargs,
) -> BaseChatModel:
    """创建 DeepSeek 对话模型

    Args:
        model_name: 模型名称（deepseek-v4-flash 等）
        temperature: 采样温度
        **kwargs: 传递给 ChatDeepSeek 的额外参数

    Returns:
        ChatDeepSeek 实例
    """
    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=model_name,
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        api_base="https://api.deepseek.com",
        temperature=temperature,
        **kwargs,
    )


def create_embedding_model(
    model_name: str = "",
    **kwargs,
) -> Embeddings:
    """DeepSeek 不提供嵌入模型

    Raises:
        NotImplementedError: 始终抛出，请使用 qwen 提供商的嵌入模型
    """
    raise NotImplementedError(
        "DeepSeek 不提供嵌入模型，请使用 qwen 提供商的 DashScope 嵌入。"
        "在 agent.yaml 中设置 embedding_model_provider: qwen 即可。"
    )
