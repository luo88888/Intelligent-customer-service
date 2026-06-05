"""OpenAI / ChatGPT 模型提供商

对话模型通过 langchain_openai.ChatOpenAI 创建。
嵌入模型通过 langchain_openai.OpenAIEmbeddings 创建。

所需环境变量: OPENAI_API_KEY
"""
import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings


def create_chat_model(
    model_name: str = "gpt-5.4-nano",
    temperature: float = 0.0,
    **kwargs,
) -> BaseChatModel:
    """创建 OpenAI 对话模型

    Args:
        model_name: 模型名称（gpt-5.4-nano, gpt-4o, gpt-4o-mini 等）
        temperature: 采样温度
        **kwargs: 传递给 ChatOpenAI 的额外参数

    Returns:
        ChatOpenAI 实例
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        api_key=os.environ.get("OPENAI_API_KEY"),
        temperature=temperature,
        **kwargs,
    )


def create_embedding_model(
    model_name: str = "text-embedding-3-small",
    **kwargs,
) -> Embeddings:
    """创建 OpenAI 嵌入模型

    Args:
        model_name: 嵌入模型名称（text-embedding-3-small, text-embedding-3-large 等）
        **kwargs: 传递给 OpenAIEmbeddings 的额外参数

    Returns:
        OpenAIEmbeddings 实例
    """
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=model_name,
        api_key=os.environ.get("OPENAI_API_KEY"),
        **kwargs,
    )
