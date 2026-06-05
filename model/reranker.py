"""
重排序模型模块

提供两种后端：
- DashScopeReranker: 基于阿里云 DashScope gte-rerank API（默认，无需本地模型）
- FlagEmbeddingReranker: 基于本地 BGE-Reranker 模型（需安装 FlagEmbedding）
"""
from abc import ABC, abstractmethod
from langchain_core.documents import Document

from utils.logger_handler import logger


class BaseReranker(ABC):
    """重排序抽象基类"""

    @abstractmethod
    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        """对文档列表进行重排序，返回 Top-N 结果

        Args:
            query: 用户查询
            documents: 待重排序的文档列表
            top_n: 返回的文档数量

        Returns:
            按相关性降序排列的 Top-N 文档
        """
        pass


class DashScopeReranker(BaseReranker):
    """基于 DashScope TextReRank API 的重排序器

    使用阿里云的 gte-rerank 模型，对中文文本有良好支持。
    """

    def __init__(self, model_name: str = "gte-rerank"):
        """初始化 DashScope 重排序器

        Args:
            model_name: DashScope 重排序模型名称，默认 gte-rerank
        """
        self.model_name = model_name
        logger.info(f"[DashScopeReranker] 初始化完成，模型: {model_name}")

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        """调用 DashScope TextReRank API 进行重排序

        Args:
            query: 用户查询
            documents: 待重排序的文档列表
            top_n: 返回的文档数量

        Returns:
            按相关性降序排列的 Top-N 文档

        Raises:
            ImportError: dashscope 包未安装
        """
        import dashscope
        from http import HTTPStatus

        if not documents:
            return []

        # 准备文档内容列表
        doc_texts = [doc.page_content for doc in documents]

        # 调用 DashScope TextReRank API
        resp = dashscope.TextReRank.call(
            model=self.model_name,
            query=query,
            documents=doc_texts,
            top_n=min(top_n, len(documents)),
            return_documents=False,  # 只返回索引和分数，不返回原文
        )

        if resp.status_code != HTTPStatus.OK:
            logger.error(f"[DashScopeReranker] API 调用失败: status={resp.status_code}, msg={resp.message}")
            # 降级：返回原始排序的前 top_n 个文档
            return documents[:top_n]

        # 按 API 返回的 relevance_score 排序，取 top_n
        sorted_results = sorted(
            resp.output.results,
            key=lambda x: x.relevance_score,
            reverse=True
        )[:top_n]

        reranked = [documents[result.index] for result in sorted_results]
        logger.info(
            f"[DashScopeReranker] 重排序完成: {len(documents)} -> {len(reranked)}, "
            f"top_score={sorted_results[0].relevance_score:.4f}" if sorted_results else ""
        )
        return reranked


class FlagEmbeddingReranker(BaseReranker):
    """基于 FlagEmbedding (BAAI/bge-reranker) 的本地重排序器

    需要安装 FlagEmbedding: pip install FlagEmbedding
    首次使用时会自动下载模型（约 2GB）。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """初始化 FlagEmbedding 重排序器

        Args:
            model_name: HuggingFace 模型名称
        """
        self.model_name = model_name
        self._model = None  # 延迟加载
        logger.info(f"[FlagEmbeddingReranker] 初始化完成，模型: {model_name}（延迟加载）")

    def _load_model(self):
        """延迟加载 FlagEmbedding 模型"""
        if self._model is None:
            from FlagEmbedding import FlagReranker
            logger.info(f"[FlagEmbeddingReranker] 正在加载模型: {self.model_name} ...")
            self._model = FlagReranker(self.model_name, use_fp16=True)
            logger.info(f"[FlagEmbeddingReranker] 模型加载完成")

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        """使用本地 BGE-Reranker 模型进行重排序

        Args:
            query: 用户查询
            documents: 待重排序的文档列表
            top_n: 返回的文档数量

        Returns:
            按相关性降序排列的 Top-N 文档
        """
        self._load_model()

        if not documents:
            return []

        # 构造 (query, doc) 对
        pairs = [[query, doc.page_content] for doc in documents]

        # 批量计算分数
        scores = self._model.compute_score(pairs, normalize=True)

        # 处理单个文档的情况（返回标量而非列表）
        if isinstance(scores, float):
            scores = [scores]

        # 按分数降序排列
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in indexed_scores[:top_n]]

        logger.info(f"[FlagEmbeddingReranker] 重排序完成: {len(documents)} -> {len(top_indices)}")
        return [documents[i] for i in top_indices]


def create_reranker(backend: str = "dashscope", model_name: str = "gte-rerank") -> BaseReranker:
    """重排序器工厂函数

    Args:
        backend: 后端类型，支持 "dashscope" 和 "flagembedding"
        model_name: 模型名称

    Returns:
        BaseReranker 实例

    Raises:
        ValueError: 未知的 backend 类型
    """
    backend_map = {
        "dashscope": DashScopeReranker,
        "flagembedding": FlagEmbeddingReranker,
    }

    if backend not in backend_map:
        raise ValueError(f"未知的重排序后端: {backend}，支持: {list(backend_map.keys())}")

    return backend_map[backend](model_name=model_name)


# python -m model.reranker
if __name__ == "__main__":
    from utils.config_handler import rag_conf

    reranker_conf = rag_conf.get("reranker", {})
    reranker = create_reranker(
        backend=reranker_conf.get("backend", "dashscope"),
        model_name=reranker_conf.get("model_name", "gte-rerank"),
    )

    # 模拟文档测试
    from langchain_core.documents import Document
    test_docs = [
        Document(page_content="扫地机器人日常维护包括清理尘盒、清洗拖布、检查边刷是否缠绕毛发。"),
        Document(page_content="小户型（80平米以下）推荐选择机身轻薄、转弯灵活的扫拖一体机器人，如追觅X30、石头G20等型号。"),
        Document(page_content="开不了机时首先检查电源是否接通，长按电源键3秒以上尝试强制开机。"),
    ]
    query = "小户型适合什么扫地机器人"

    print(f"查询: {query}\n")
    results = reranker.rerank(query, test_docs, top_n=2)
    for i, doc in enumerate(results):
        print(f"\n--- 重排序后第 {i+1} 名 ---")
        print(doc.page_content)
