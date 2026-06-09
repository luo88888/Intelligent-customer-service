"""
混合检索编排模块

编排 Milvus 原生混合检索（Dense + BM25 + RRF）与 DashScope Reranker，
支持 Multi-Query 改写和 HyDE 查询增强。
实现 LangChain retriever 兼容接口。
"""
from __future__ import annotations

from typing import Optional

from langchain_core.documents import Document

from rag.query_processor import QueryProcessor, deduplicate_documents
from utils.config_handler import rag_conf
from utils.logger_handler import logger


class HybridRetriever:
    """混合检索器：Milvus Hybrid Search + 可选 Reranker + 可选查询增强

    检索流程:
    1. [可选] QueryProcessor 对查询进行增强（Multi-Query / HyDE）
    2. 对每个查询执行 Milvus Dense + BM25 + RRF 混合检索
    3. 合并多查询结果并去重
    4. [可选] Reranker 对合并结果精排
    5. 返回 Top final_k 文档
    """

    def __init__(
        self,
        vector_store_service,
        reranker_service: Optional[object] = None,
        dense_k: int = 10,
        sparse_k: int = 10,
        rrf_k: int = 60,
        final_k: int = 3,
        rerank_enabled: bool = True,
        max_rerank_input: int = 25,
        query_processor: Optional[QueryProcessor] = None,
    ):
        """初始化混合检索器

        Args:
            vector_store_service: VectorStoreService 实例
            reranker_service: BaseReranker 实例（可选）
            dense_k: Dense 检索候选数
            sparse_k: Sparse 检索候选数
            rrf_k: RRF 融合常数
            final_k: 最终返回文档数
            rerank_enabled: 是否启用重排序
            max_rerank_input: Reranker 最大输入文档数（Multi-Query 合并后可能很多，需截断）
            query_processor: QueryProcessor 实例（可选），用于 Multi-Query / HyDE
        """
        self.vs = vector_store_service
        self.reranker = reranker_service
        self.dense_k = dense_k
        self.sparse_k = sparse_k
        self.rrf_k = rrf_k
        self.final_k = final_k
        self.rerank_enabled = rerank_enabled
        self.max_rerank_input = max_rerank_input
        self.query_processor = query_processor

        # 诊断信息
        features = []
        if query_processor is not None:
            if query_processor.multi_query_enabled:
                features.append("Multi-Query")
            if query_processor.hyde_enabled:
                features.append("HyDE")
        features.append("Dense+BM25+RRF")
        if rerank_enabled and reranker_service is not None:
            features.append("Reranker")
        logger.info(f"[HybridRetriever] 初始化完成，检索链路: {' → '.join(features)}")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def invoke(self, query: str) -> list[Document]:
        """执行检索

        如果配置了 QueryProcessor，先对查询进行增强（Multi-Query / HyDE），
        然后对每个变体分别检索，合并去重后再精排。

        Args:
            query: 用户查询

        Returns:
            Document 列表（长度 ≤ final_k）
        """
        if self.query_processor is not None:
            return self._multi_query_retrieve(query)
        else:
            return self._single_query_retrieve(query)

    # ------------------------------------------------------------------
    # 单查询检索（原有逻辑，向后兼容）
    # ------------------------------------------------------------------

    def _single_query_retrieve(self, query: str) -> list[Document]:
        """单查询检索：hybrid_search → rerank → return"""
        merged = self._do_hybrid_search(query)

        if not merged:
            logger.warning("[HybridRetriever] 混合检索无结果，降级到纯 Dense")
            return self.vs.dense_search(query, k=self.final_k)

        final = self._apply_rerank(query, merged)
        return final

    # ------------------------------------------------------------------
    # 多查询检索（Multi-Query / HyDE）
    # ------------------------------------------------------------------

    def _multi_query_retrieve(self, query: str) -> list[Document]:
        """多查询检索：逐查询检索 → 合并去重 → 精排

        流程:
        1. QueryProcessor.process(query) → [q1, q2, ..., qN]
        2. 对每个 qi 执行 hybrid_search（不精排）
        3. 合并所有结果，去重
        4. 截断到 max_rerank_input，送入 Reranker
        5. 返回 top final_k
        """
        # Step 1: 查询增强
        queries = self.query_processor.process(query)
        logger.info(f"[HybridRetriever] 查询增强: {len(queries)} 个变体")

        # Step 2: 对每个查询变体执行混合检索
        all_docs: list[Document] = []
        for i, q in enumerate(queries):
            docs = self._do_hybrid_search(q)
            if docs:
                logger.debug(f"[HybridRetriever] 变体 {i+1}/{len(queries)} 检索到 {len(docs)} 篇")
                all_docs.extend(docs)

        if not all_docs:
            logger.warning("[HybridRetriever] 所有变体均无结果，降级到原始查询 Dense 检索")
            return self.vs.dense_search(query, k=self.final_k)

        # Step 3: 去重
        before_dedup = len(all_docs)
        all_docs = deduplicate_documents(all_docs)
        logger.info(
            f"[HybridRetriever] 合并去重: {before_dedup} → {len(all_docs)} 篇"
        )

        # TODO: 优先级 5，rerank_enabled=False 时，直接截断到 final_k
        # Step 4: 截断 → 精排
        if len(all_docs) > self.max_rerank_input:
            logger.info(
                f"[HybridRetriever] 文档数 {len(all_docs)} 超过 max_rerank_input({self.max_rerank_input})，截断"
            )
            all_docs = all_docs[:self.max_rerank_input]

        # Step 5: Reranker 精排（使用原始查询）
        final = self._apply_rerank(query, all_docs)
        return final

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _do_hybrid_search(self, query: str) -> list[Document]:
        """执行一次检索（根据配置选择混合或纯 Dense）

        当 hybrid_search.enabled=true 时使用 Milvus Dense+BM25+RRF；
        否则降级为纯 Dense 检索。返回的候选数会多于 final_k，
        为后续合并和精排留空间。

        Args:
            query: 查询字符串

        Returns:
            Document 列表
        """
        hs_conf = rag_conf.get("hybrid_search", {})
        if hs_conf.get("enabled", False):
            return self.vs.hybrid_search(
                query=query,
                dense_k=self.dense_k,
                sparse_k=self.sparse_k,
                rrf_k=self.rrf_k,
                final_k=max(self.final_k * 2, self.dense_k + self.sparse_k),
            )
        else:
            # 纯 Dense 模式
            return self.vs.dense_search(query, k=max(self.final_k * 2, 10))

    def _apply_rerank(self, query: str, docs: list[Document]) -> list[Document]:
        """对文档列表进行重排序（如果启用），返回 Top final_k

        Args:
            query: 用户原始查询
            docs: 待精排的文档列表

        Returns:
            精排后的 Top final_k 文档
        """
        if not docs:
            return []

        if self.rerank_enabled and self.reranker is not None and len(docs) > self.final_k:
            final = self.reranker.rerank(query, docs, self.final_k)
            logger.info(
                f"[HybridRetriever] Reranker 精排: {len(docs)} → {len(final)}"
            )
            return final

        return docs[:self.final_k]


# python -m rag.hybrid_retriever
if __name__ == "__main__":
    from rag.vector_store import VectorStoreService
    from model.factory import create_reranker, create_chat_model
    from rag.query_processor import QueryProcessor, create_query_processor
    from utils.config_handler import rag_conf

    vs = VectorStoreService()
    hs_conf = rag_conf.get("hybrid_search", {})
    reranker_conf = rag_conf.get("reranker", {})

    # 创建 Reranker
    reranker = (
        create_reranker(
            backend=reranker_conf.get("backend", "dashscope"),
            model_name=reranker_conf.get("model_name", "gte-rerank"),
        )
        if reranker_conf.get("enabled", True)
        else None
    )

    # 创建 QueryProcessor
    qp = create_query_processor()

    retriever = HybridRetriever(
        vector_store_service=vs,
        reranker_service=reranker,
        dense_k=hs_conf.get("dense_k", 10),
        sparse_k=hs_conf.get("sparse_k", 10),
        rrf_k=hs_conf.get("rrf_k", 60),
        final_k=hs_conf.get("final_k", 3),
        rerank_enabled=reranker_conf.get("enabled", True),
        max_rerank_input=reranker_conf.get("max_input_docs", 25),
        query_processor=qp,
    )

    query = "小户型适合哪些扫地机器人"
    print(f"查询: {query}")
    print("=" * 50)

    docs = retriever.invoke(query)
    for i, doc in enumerate(docs, 1):
        print(f"\n--- 结果 {i} ---")
        print(f"内容: {doc.page_content[:200]}")
        print(f"来源: {doc.metadata.get('source', 'unknown')}")
