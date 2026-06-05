"""
RAG 服务模块

支持两种检索模式:
- 混合模式（hybrid_search.enabled=true）：Milvus Dense + BM25 + RRF + Reranker
- 纯 Dense 模式（hybrid_search.enabled=false）：Milvus Dense 检索（向后兼容）

支持查询增强（config/rag.yaml → query_processing）:
- Multi-Query：多角度查询改写，合并检索结果
- HyDE：假设性文档嵌入
"""
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from rag.vector_store import VectorStoreService
from rag.hybrid_retriever import HybridRetriever
from rag.query_processor import create_query_processor
from model.factory import create_reranker
from utils.prompt_loader import load_rag_prompt
from utils.config_handler import rag_conf
from utils.logger_handler import logger
from model.factory import chat_model


def print_prompt(prompt):
    print("=" * 20)
    print(prompt.to_string())
    print("=" * 20)
    return prompt


class RAGSummarizeService:
    """RAG 摘要服务，检索 + LLM 生成"""

    def __init__(self):
        # 向量存储服务
        self.vector_store_service = VectorStoreService()

        # 查询处理器（Multi-Query / HyDE），可能为 None
        self.query_processor = create_query_processor()

        # 根据配置选择检索器
        hs_conf = rag_conf.get("hybrid_search", {})
        self.hybrid_enabled = hs_conf.get("enabled", False)
        has_query_processing = self.query_processor is not None

        if self.hybrid_enabled or has_query_processing:
            # 混合检索 或 有查询增强 → 使用 HybridRetriever 编排
            self._init_hybrid_retriever(hs_conf)
        else:
            # 纯 Dense 模式（无查询增强，向后兼容）
            self.retriever = self.vector_store_service
            logger.info("[RAGSummarizeService] 使用纯 Dense 检索模式")

        # 提示词与模型链
        self.prompt_text = load_rag_prompt()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_hybrid_retriever(self, hs_conf: dict) -> None:
        """初始化混合检索器（BM25 + Dense + RRF + Reranker + 可选查询增强）"""
        reranker_conf = rag_conf.get("reranker", {})

        # 创建 Reranker
        reranker = None
        reranker_enabled = reranker_conf.get("enabled", True)
        if reranker_enabled:
            try:
                reranker = create_reranker(
                    backend=reranker_conf.get("backend", "dashscope"),
                    model_name=reranker_conf.get("model_name", "gte-rerank"),
                )
            except Exception as e:
                logger.warning(f"[RAGSummarizeService] Reranker 创建失败，将跳过重排序: {e}")
                reranker_enabled = False

        self.retriever = HybridRetriever(
            vector_store_service=self.vector_store_service,
            reranker_service=reranker,
            dense_k=hs_conf.get("dense_k", 10),
            sparse_k=hs_conf.get("sparse_k", 10),
            rrf_k=hs_conf.get("rrf_k", 60),
            final_k=hs_conf.get("final_k", 3),
            rerank_enabled=reranker_enabled,
            max_rerank_input=reranker_conf.get("max_input_docs", 25),
            query_processor=self.query_processor,
        )

        mode_parts = []
        if self.hybrid_enabled:
            mode_parts.append("Dense + BM25 + RRF")
        else:
            mode_parts.append("纯 Dense")
        if self.query_processor is not None:
            qp_parts = []
            if self.query_processor.multi_query_enabled:
                qp_parts.append("Multi-Query")
            if self.query_processor.hyde_enabled:
                qp_parts.append("HyDE")
            mode_parts.append(" + ".join(qp_parts))
        if reranker_enabled:
            mode_parts.append("Reranker")
        logger.info(f"[RAGSummarizeService] 检索模式: {' + '.join(mode_parts)}")

    def _init_chain(self):
        """构建 LCEL 链: Prompt → LLM → 文本输出"""
        return self.prompt_template | self.model | StrOutputParser()

    def retriever_docs(self, query: str) -> list[Document]:
        """检索相关文档

        Args:
            query: 用户查询

        Returns:
            Document 列表
        """
        return self.retriever.invoke(query)

    def rag_summarize(self, query: str) -> str:
        """RAG 摘要：检索 + LLM 生成答案

        Args:
            query: 用户查询

        Returns:
            生成的答案字符串
        """
        context_docs = self.retriever_docs(query)
        context = self._format_context(context_docs)
        return self.chain.invoke({"input": query, "context": context})

    def rag_summarize_with_context(self, query: str) -> tuple[str, str]:
        """RAG 摘要 + 返回检索上下文（供评估管道使用）

        Args:
            query: 用户查询

        Returns:
            (answer, context) 元组，context 为格式化后的拼接字符串
        """
        context_docs = self.retriever_docs(query)
        context = self._format_context(context_docs)
        answer = self.chain.invoke({"input": query, "context": context})
        return answer, context

    def rag_summarize_with_docs(self, query: str) -> tuple[str, list[str]]:
        """RAG 摘要 + 返回独立文档列表（供 RAGAS 评估使用）

        RAGAS 的 context_precision / context_recall 需要逐文档计算，
        拼接后的字符串会导致指标失真，因此需要独立文档列表。

        Args:
            query: 用户查询

        Returns:
            (answer, doc_texts) 元组，doc_texts 为独立文档内容列表
        """
        context_docs = self.retriever_docs(query)
        doc_texts = [doc.page_content for doc in context_docs]
        context = self._format_context(context_docs)
        answer = self.chain.invoke({"input": query, "context": context})
        return answer, doc_texts

    def _format_context(self, docs: list[Document]) -> str:
        """将 Document 列表格式化为提示词中的参考上下文

        Args:
            docs: 检索到的文档列表

        Returns:
            格式化的上下文字符串
        """
        context = ""
        for counter, doc in enumerate(docs, 1):
            context += f"【参考资料{counter}】：{doc.page_content} | 参考元数据：{doc.metadata}\n\n"
        return context

    # ==================== 文档管理（透传给 VectorStoreService） ====================

    def get_document_sources(self) -> list[str]:
        """获取已入库的所有文档来源列表

        Returns:
            去重后的文件路径列表
        """
        return self.vector_store_service.get_sources()

    def get_document_count(self) -> int:
        """获取集合中的文档块总数

        Returns:
            文档块数量
        """
        return self.vector_store_service._get_document_count()

    def delete_document_by_source(self, source: str) -> int:
        """删除指定来源的所有文档块

        Args:
            source: 文件路径（需与入库时的 source 完全一致）

        Returns:
            删除的条目数
        """
        return self.vector_store_service.delete_by_source(source)

    def delete_document_by_ids(self, ids: list[int]) -> int:
        """按主键 ID 删除指定文档块

        Args:
            ids: 待删除的文档块 ID 列表

        Returns:
            删除的条目数
        """
        return self.vector_store_service.delete_by_ids(ids)

    def update_document(self, source: str) -> int:
        """更新指定来源的文档：先删除旧条目，再重新加载文件

        Args:
            source: 文件路径

        Returns:
            新插入的文档块数量
        """
        return self.vector_store_service.update_source(source)

    def rebuild_indexes(self) -> None:
        """重建 BM25 索引（加载新文档后调用）"""
        if self.hybrid_enabled and hasattr(self.retriever, 'bm25'):
            docs = self.vector_store_service.get_all_documents()
            if hasattr(self.retriever, 'bm25_service'):
                self.retriever.bm25_service.build_index(docs)
                logger.info(f"[RAGSummarizeService] BM25 索引已重建: {len(docs)} 篇文档")


# python -m rag.rag_service
if __name__ == "__main__":
    query = "小户型适合哪些扫地机器人？"
    rag_service = RAGSummarizeService()
    print(f"查询: {query}")
    print("=" * 50)

    # 展示检索到的文档
    docs = rag_service.retriever_docs(query)
    print("\n检索到的参考文档:")
    for i, doc in enumerate(docs, 1):
        print(f"  [{i}] {doc.page_content[:100]}...")
        print(f"      来源: {doc.metadata.get('source', 'unknown')}")

    # 生成答案
    print("\n" + "=" * 50)
    print("LLM 生成答案:")
    answer = rag_service.rag_summarize(query)
    print(answer)
