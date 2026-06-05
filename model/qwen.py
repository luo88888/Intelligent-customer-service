"""
Qwen / Tongyi 模型提供商

对话模型通过 langchain_community.chat_models.tongyi.ChatTongyi 创建。
嵌入模型通过 langchain_community.embeddings.DashScopeEmbeddings 创建。

API Key 由底层 SDK 自动从 DASHSCOPE_API_KEY 环境变量读取，无需显式传参。
"""
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings


def create_chat_model(
    model_name: str = "qwen-plus",
    **kwargs,
) -> BaseChatModel:
    """创建 Qwen/Tongyi 对话模型

    Args:
        model_name: 模型名称（qwen-plus, qwen-max, qwen-turbo 等）
        **kwargs: 传递给 ChatTongyi 的额外参数（temperature, top_p 等）

    Returns:
        ChatTongyi 实例
    """
    from langchain_community.chat_models.tongyi import ChatTongyi

    return ChatTongyi(model=model_name, **kwargs)


def create_embedding_model(
    model_name: str = "text-embedding-v4",
    **kwargs,
) -> Embeddings:
    """创建 DashScope 嵌入模型

    Args:
        model_name: 嵌入模型名称（text-embedding-v4 等）
        **kwargs: 传递给 DashScopeEmbeddings 的额外参数

    Returns:
        DashScopeEmbeddings 实例
    """
    from langchain_community.embeddings import DashScopeEmbeddings

    return DashScopeEmbeddings(model=model_name, **kwargs)
