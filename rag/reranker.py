"""
向后兼容转发层

重排序器实现已迁移至 model.reranker。
所有已有的 from rag.reranker import ... 导入继续有效。
新代码请从 model.factory 或 model.reranker 导入。
"""
from model.reranker import (
    BaseReranker,
    DashScopeReranker,
    FlagEmbeddingReranker,
    create_reranker,
)

__all__ = [
    "BaseReranker",
    "DashScopeReranker",
    "FlagEmbeddingReranker",
    "create_reranker",
]
