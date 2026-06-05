"""
统一模型工厂

提供配置驱动的对话模型、嵌入模型和重排序器创建。
提供商通过 YAML 配置决定，切换提供商无需修改代码。

模块级单例 chat_model 和 embedding_model 保持向后兼容。
"""
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from utils.config_handler import agent_conf, rag_conf


# ---------------------------------------------------------------------------
# 提供商分发映射
# ---------------------------------------------------------------------------

_CHAT_PROVIDERS = {
    "qwen": "model.qwen",
    "deepseek": "model.deepseek",
    "openai": "model.openai",
}

_EMBEDDING_PROVIDERS = {
    "qwen": "model.qwen",
    "deepseek": "model.deepseek",
    "openai": "model.openai",
}


def _import_provider(module_path: str, func_name: str):
    """懒加载导入提供商模块的指定函数"""
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


# ---------------------------------------------------------------------------
# 公开工厂函数
# ---------------------------------------------------------------------------


def create_chat_model(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    **kwargs,
) -> BaseChatModel:
    """基于配置创建对话模型

    提供商和模型名从 config/agent.yaml 读取，支持显式覆盖。

    Args:
        provider: 提供商标识（"qwen", "deepseek"），默认从 agent_conf 读取
        model_name: 模型名覆盖，默认从 agent_conf 读取
        **kwargs: 传递给提供商 create_chat_model 的额外参数（如 temperature）

    Returns:
        BaseChatModel 实例

    Raises:
        ValueError: 配置的提供商未知
    """
    if provider is None:
        provider = agent_conf.get("chat_model_provider", "deepseek")
    if model_name is None:
        model_name = agent_conf.get("chat_model_name", "deepseek-v4-flash")

    if provider not in _CHAT_PROVIDERS:
        raise ValueError(
            f"未知的对话模型提供商: '{provider}'，"
            f"支持: {list(_CHAT_PROVIDERS.keys())}"
        )

    module_path = _CHAT_PROVIDERS[provider]
    _create = _import_provider(module_path, "create_chat_model")
    return _create(model_name=model_name, **kwargs)


def create_embedding_model(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    **kwargs,
) -> Embeddings:
    """基于配置创建嵌入模型

    提供商和模型名从 config/agent.yaml 读取，支持显式覆盖。

    Args:
        provider: 提供商标识（"qwen"），默认从 agent_conf 读取
        model_name: 模型名覆盖，默认从 agent_conf 读取
        **kwargs: 传递给提供商 create_embedding_model 的额外参数

    Returns:
        Embeddings 实例

    Raises:
        ValueError: 配置的提供商未知
    """
    if provider is None:
        provider = agent_conf.get("embedding_model_provider", "qwen")
    if model_name is None:
        model_name = agent_conf.get("embedding_model_name", "text-embedding-v4")

    if provider not in _EMBEDDING_PROVIDERS:
        raise ValueError(
            f"未知的嵌入模型提供商: '{provider}'，"
            f"支持: {list(_EMBEDDING_PROVIDERS.keys())}"
        )

    module_path = _EMBEDDING_PROVIDERS[provider]
    _create = _import_provider(module_path, "create_embedding_model")
    return _create(model_name=model_name, **kwargs)


def create_reranker(
    backend: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """基于配置创建重排序器

    Backend 和模型名从 config/rag.yaml 读取，支持显式覆盖。

    Args:
        backend: 重排序后端（"dashscope", "flagembedding"），默认从 rag_conf 读取
        model_name: 重排序模型名，默认从 rag_conf 读取

    Returns:
        BaseReranker 实例

    Raises:
        ValueError: 配置的后端未知
    """
    from model.reranker import create_reranker as _create_reranker

    reranker_conf = rag_conf.get("reranker", {})
    if backend is None:
        backend = reranker_conf.get("backend", "dashscope")
    if model_name is None:
        model_name = reranker_conf.get("model_name", "gte-rerank")

    return _create_reranker(backend=backend, model_name=model_name)


# ---------------------------------------------------------------------------
# 向后兼容的模块级单例
# ---------------------------------------------------------------------------

chat_model = create_chat_model()
embedding_model = create_embedding_model()
