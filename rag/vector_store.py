"""
向量存储服务模块（Milvus 向量数据库）

基于 pymilvus + milvus-lite 实现嵌入式向量存储，原生支持：
- Dense 向量检索（COSINE 相似度）
- Sparse BM25 检索（中文分词）
- 混合检索（Dense + Sparse + RRF 融合）
- MD5 文档去重加载
"""
import os
import threading
from typing import Optional, Callable
from pymilvus import MilvusClient, DataType, Function, FunctionType
from pymilvus.client.abstract import AnnSearchRequest, RRFRanker
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config_handler import rag_conf, chroma_conf
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
from model.factory import embedding_model


class VectorStoreService:
    """Milvus 向量存储服务，管理文档嵌入、存储与检索"""

    def __init__(self):
        # Milvus 配置（从 rag.yaml，fallback 到旧 chroma.yaml）
        milvus_conf = rag_conf.get("milvus", {})
        self.db_path = get_abs_path(milvus_conf.get("db_path", "milvus.db"))
        self.collection_name = milvus_conf.get("collection_name", "rag_collection")
        self.embedding_dim = 1024  # text-embedding-v4

        # 文档加载配置（从 chroma.yaml 兼容读取）
        self.data_path = get_abs_path(chroma_conf.get("data_path", "data"))
        self.md5_store_path = get_abs_path(chroma_conf.get("md5_hex_store", "md5.txt"))
        self.allowed_types = tuple(chroma_conf.get("allowed_knowledge_file_type", ["txt", "pdf"]))

        # 文本分块器（从 chroma.yaml 读取参数）
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf.get("chunk_size", 200),
            chunk_overlap=chroma_conf.get("chunk_overlap", 20),
            separators=chroma_conf.get("separators", ["\n\n", "\n", "。", ".", "？", "!", "；", " ", ""]),
            length_function=len,
        )

        # 初始化 Milvus 客户端（关闭闲置 keepalive pings，避免 too_many_pings GOAWAY）
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        self.client = MilvusClient(
            self.db_path,
            grpc_options={
                "grpc.keepalive_time_ms": 60000,            # ping 间隔从 10s → 60s
                "grpc.keepalive_permit_without_calls": False,  # 闲置时不发 ping
            },
        )

        # Milvus Lite 高并发保护：限制同时进行的 gRPC 搜索请求数
        self._search_semaphore = threading.BoundedSemaphore(16)

        # 确保集合存在并加载到内存
        self._ensure_collection()
        self._load_collection()

        count = self._get_document_count()
        logger.info(f"[VectorStoreService] 初始化完成，集合: {self.collection_name}，文档数: {count}")

    # ==================== 集合管理 ====================

    def _ensure_collection(self) -> None:
        """确保 Milvus 集合存在，不存在则创建（含 BM25 Function + 索引）"""
        if self.client.has_collection(self.collection_name):
            return

        logger.info(f"[VectorStoreService] 创建集合: {self.collection_name}")

        # 1. 构建 Schema
        schema = self.client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=65535, enable_analyzer=True)
        schema.add_field("source", DataType.VARCHAR, max_length=1024)         # 来源文件路径
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self.embedding_dim)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)       # BM25 函数输出

        # 2. BM25 函数
        bm25_fn = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["text"],
            output_field_names=["sparse_vector"],
        )
        schema.add_function(bm25_fn)

        # 3. 索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="dense_vector", index_type="AUTOINDEX", metric_type="COSINE")
        index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")

        # 4. 创建集合
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"[VectorStoreService] 集合 {self.collection_name} 创建完成")

    def _load_collection(self) -> None:
        """将集合加载到内存（Milvus Lite 需要显式调用）"""
        try:
            self.client.load_collection(self.collection_name)
            logger.info(f"[VectorStoreService] 集合 {self.collection_name} 已加载到内存")
        except Exception as e:
            logger.warning(f"[VectorStoreService] 集合加载失败（可能已加载）: {e}")

    def _get_document_count(self) -> int:
        """获取集合中的文档数量"""
        try:
            if not self.client.has_collection(self.collection_name):
                return 0
            stats = self.client.get_collection_stats(self.collection_name)
            return stats.get("row_count", 0)
        except Exception:
            return 0

    # ==================== 检索接口 ====================

    def get_retriever(self):
        """返回 self，支持 .invoke(query) 接口"""
        return self

    def invoke(self, query: str) -> list[Document]:
        """LangChain retriever 兼容接口 — 执行混合检索（如果启用）或纯 Dense 检索

        Args:
            query: 用户查询

        Returns:
            Document 列表
        """
        hs_conf = rag_conf.get("hybrid_search", {})
        if hs_conf.get("enabled", False):
            return self.hybrid_search(
                query=query,
                dense_k=hs_conf.get("dense_k", 10),
                sparse_k=hs_conf.get("sparse_k", 10),
                rrf_k=hs_conf.get("rrf_k", 60),
                final_k=hs_conf.get("final_k", 3),
            )
        else:
            return self.dense_search(query, k=hs_conf.get("final_k", 3))

    def dense_search(self, query: str, k: int = 3) -> list[Document]:
        """纯 Dense 向量检索

        Args:
            query: 用户查询
            k: 返回文档数量

        Returns:
            Document 列表
        """
        try:
            query_embedding = [embedding_model.embed_query(query)]
            with self._search_semaphore:
                results = self.client.search(
                    collection_name=self.collection_name,
                    data=query_embedding,
                    anns_field="dense_vector",
                    search_params={"metric_type": "COSINE"},
                    limit=k,
                    output_fields=["text", "source"],
                )
            return self._hits_to_documents(results)
        except Exception as e:
            logger.error(f"[VectorStoreService] Dense 检索失败: {e}")
            return []

    def sparse_search(self, query: str, k: int = 10) -> list[tuple[Document, float]]:
        """BM25 稀疏检索

        Args:
            query: 用户查询（原始文本，Milvus 自动应用 BM25 函数）
            k: 返回文档数量

        Returns:
            (Document, score) 列表
        """
        try:
            # milvus-lite 中 BM25 检索需通过 hybrid_search API（仅传入 sparse 请求）
            sparse_req = AnnSearchRequest(
                data=[query],
                anns_field="sparse_vector",
                param={"metric_type": "BM25"},
                limit=k,
            )
            with self._search_semaphore:
                results = self.client.hybrid_search(
                    collection_name=self.collection_name,
                    reqs=[sparse_req],
                    ranker=RRFRanker(k=60),  # 单路请求，RRF 退化为原序
                    limit=k,
                    output_fields=["text", "source"],
                )
            docs = []
            for hits in results:
                for hit in hits:
                    doc = Document(
                        page_content=hit["entity"]["text"],
                        metadata={"source": hit["entity"].get("source", ""), "score": hit["distance"]},
                    )
                    docs.append((doc, hit["distance"]))
            return docs
        except Exception as e:
            logger.error(f"[VectorStoreService] Sparse 检索失败: {e}")
            return []

    def hybrid_search(
        self,
        query: str,
        dense_k: int = 10,
        sparse_k: int = 10,
        rrf_k: int = 60,
        final_k: int = 3,
    ) -> list[Document]:
        """混合检索：Dense + Sparse + RRF 融合

        使用 Milvus 原生 hybrid_search + RRFRanker。

        Args:
            query: 用户查询
            dense_k: Dense 候选数
            sparse_k: Sparse 候选数
            rrf_k: RRF 融合常数
            final_k: 最终返回数量

        Returns:
            Document 列表
        """
        try:
            # Dense 请求：需要嵌入向量
            query_embedding = [embedding_model.embed_query(query)]
            dense_req = AnnSearchRequest(
                data=query_embedding,
                anns_field="dense_vector",
                param={"metric_type": "COSINE"},
                limit=dense_k,
            )

            # Sparse 请求：直接传文本，Milvus 自动应用 BM25 函数
            sparse_req = AnnSearchRequest(
                data=[query],
                anns_field="sparse_vector",
                param={"metric_type": "BM25"},
                limit=sparse_k,
            )

            with self._search_semaphore:
                results = self.client.hybrid_search(
                    collection_name=self.collection_name,
                    reqs=[dense_req, sparse_req],
                    ranker=RRFRanker(k=rrf_k),
                    limit=final_k,
                    output_fields=["text", "source"],
                )

            return self._hits_to_documents(results)
        except Exception as e:
            logger.error(f"[VectorStoreService] 混合检索失败，降级到 Dense 检索: {e}")
            return self.dense_search(query, k=final_k)

    @staticmethod
    def _hits_to_documents(results: list) -> list[Document]:
        """将 Milvus 搜索结果转换为 LangChain Document 列表

        Args:
            results: Milvus search/hybrid_search 返回的 hits 列表

        Returns:
            Document 列表
        """
        docs = []
        for hits in results:
            for hit in hits:
                entity = hit["entity"]
                doc = Document(
                    page_content=entity["text"],
                    metadata={
                        "source": entity.get("source", ""),
                        "id": hit["id"],
                        "score": hit.get("distance", 0.0),
                    },
                )
                docs.append(doc)
        return docs

    # ==================== 文档加载 ====================

    def get_all_documents(self) -> list[Document]:
        """获取集合中全部文档（供外部检查/重建索引用）

        Returns:
            Document 列表
        """
        try:
            if not self.client.has_collection(self.collection_name):
                return []

            # 分页获取所有文档
            all_docs = []
            offset = 0
            page_size = 1000
            while True:
                results = self.client.query(
                    collection_name=self.collection_name,
                    filter="id >= 0",
                    output_fields=["text", "source"],
                    limit=page_size,
                    offset=offset,
                )
                if not results:
                    break
                for r in results:
                    all_docs.append(Document(
                        page_content=r["text"],
                        metadata={"source": r.get("source", ""), "id": r["id"]},
                    ))
                offset += page_size
            return all_docs
        except Exception as e:
            logger.error(f"[VectorStoreService] 获取全量文档失败: {e}")
            return []

    def get_sources(self) -> list[str]:
        """获取集合中所有不重复的文档来源

        Returns:
            去重后的 source 列表
        """
        try:
            if not self.client.has_collection(self.collection_name):
                return []

            sources = set()
            offset = 0
            page_size = 1000
            while True:
                results = self.client.query(
                    collection_name=self.collection_name,
                    filter="id >= 0",
                    output_fields=["source"],
                    limit=page_size,
                    offset=offset,
                )
                if not results:
                    break
                for r in results:
                    src = r.get("source", "")
                    if src:
                        sources.add(src)
                offset += page_size
            return sorted(sources)
        except Exception as e:
            logger.error(f"[VectorStoreService] 获取来源列表失败: {e}")
            return []

    # ==================== MD5 缓存管理 ====================

    def _check_md5_hex(self, md5_for_check: str) -> bool:
        """检查 MD5 是否已在缓存中

        Args:
            md5_for_check: 待检查的 MD5 十六进制字符串

        Returns:
            是否存在
        """
        if not os.path.exists(self.md5_store_path):
            open(self.md5_store_path, "w", encoding="utf-8").close()
            return False
        with open(self.md5_store_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() == md5_for_check:
                    return True
            return False

    def _save_md5_hex(self, md5_for_save: str) -> None:
        """保存 MD5 到缓存文件

        Args:
            md5_for_save: 待保存的 MD5 十六进制字符串
        """
        with open(self.md5_store_path, "a", encoding="utf-8") as f:
            f.write(md5_for_save + "\n")

    def _remove_md5_hex(self, md5_to_remove: str) -> None:
        """从 MD5 缓存文件中移除指定 MD5 条目

        Args:
            md5_to_remove: 待移除的 MD5 十六进制字符串
        """
        if not os.path.exists(self.md5_store_path):
            return
        with open(self.md5_store_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(self.md5_store_path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip() != md5_to_remove:
                    f.write(line)
        logger.info(f"[VectorStoreService] 已从 MD5 缓存中移除: {md5_to_remove}")

    # ==================== 文档加载 ====================

    @staticmethod
    def _get_file_documents(file_path: str) -> list[Document]:
        """根据文件扩展名选择加载器

        Args:
            file_path: 文件路径

        Returns:
            Document 列表
        """
        if file_path.endswith(".txt"):
            return txt_loader(file_path)
        elif file_path.endswith(".pdf"):
            return pdf_loader(file_path)
        return []

    def _insert_file(self, file_path: str) -> int:
        """加载并嵌入单个文件，存入 Milvus

        执行完整的 加载 → 分块 → 嵌入 → 插入 流程。

        Args:
            file_path: 文件路径

        Returns:
            插入的文档块数量，失败返回 0
        """
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.error(f"[VectorStoreService] 文件不存在，无法插入: {file_path}")
            return 0

        documents = self._get_file_documents(file_path)
        if not documents:
            logger.warning(f"[VectorStoreService] 文件内容为空或异常: {file_path}")
            return 0

        # 文档分块
        chunks: list[Document] = self.splitter.split_documents(documents)
        if not chunks:
            logger.warning(f"[VectorStoreService] 分块后为空: {file_path}")
            return 0

        # 批量嵌入并插入 Milvus（每批 100 个块，避免单次请求过大）
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            insert_data = []
            for chunk in batch:
                embedding = embedding_model.embed_query(chunk.page_content)
                insert_data.append({
                    "text": chunk.page_content,
                    "source": file_path,
                    "dense_vector": embedding,
                })
            self.client.insert(
                collection_name=self.collection_name,
                data=insert_data,
            )

        # 保存 MD5 缓存
        md5_hex = get_file_md5_hex(file_path)
        if md5_hex:
            self._save_md5_hex(md5_hex)

        logger.info(f"[VectorStoreService] 文件已添加到知识库: {file_path}，共 {len(chunks)} 个文档块")
        return len(chunks)

    def load_documents(self, on_docs_added: Optional[Callable[[], None]] = None) -> list[Document] | None:
        """加载 data/ 目录下所有允许类型的文件，嵌入后存入 Milvus。

        MD5 去重：已处理过的文件不会重复加载。

        Args:
            on_docs_added: 文档新增后的回调（用于触发 BM25 索引重建等）

        Returns:
            新加载的 Document 列表，无新增时返回 None
        """
        allowed_file_paths = listdir_with_allowed_type(self.data_path, self.allowed_types)
        if not allowed_file_paths:
            logger.info("[VectorStoreService] 未找到可加载的文档文件")
            return []

        any_added = False
        for path in allowed_file_paths:
            md5_hex = get_file_md5_hex(path)
            if not md5_hex:
                continue
            if self._check_md5_hex(md5_hex):
                logger.info(f"[load_documents] 文件已存在于知识库: {path}")
                continue

            try:
                inserted = self._insert_file(path)
                if inserted > 0:
                    any_added = True
            except Exception as e:
                logger.error(f"[load_documents] 文件处理异常: {path}，异常: {str(e)}", exc_info=True)

        # 新增文档后触发回调
        if any_added and on_docs_added:
            on_docs_added()

        return None

    # ==================== 文档删除与更新 ====================

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """转义 Milvus 过滤表达式中的特殊字符（反斜杠、双引号）

        Milvus 过滤表达式使用类 SQL 语法，反斜杠为转义字符。
        Windows 路径中的 ``\\`` 会被误解析，需要转义。

        Args:
            value: 原始字符串

        Returns:
            转义后的字符串
        """
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def delete_by_source(self, source: str) -> int:
        """删除指定来源的所有文档块，并同步清理 MD5 缓存

        Args:
            source: 文件路径（需与入库时的 source 完全一致）

        Returns:
            删除的条目数
        """
        try:
            if not self.client.has_collection(self.collection_name):
                logger.warning(f"[VectorStoreService] 集合不存在，无法删除")
                return 0

            escaped_source = self._escape_filter_value(source)

            # 1. 查询该 source 下的条目数
            results = self.client.query(
                collection_name=self.collection_name,
                filter=f'source == "{escaped_source}"',
                output_fields=["id"],
            )
            count = len(results)
            if count == 0:
                logger.info(f"[VectorStoreService] 未找到匹配的文档，来源: {source}")
                return 0

            # 2. 按 source 过滤删除
            self.client.delete(
                collection_name=self.collection_name,
                filter=f'source == "{escaped_source}"',
            )

            # 3. 从 MD5 缓存中移除（防止因路径变化导致 MD5 计算失败）
            try:
                md5 = get_file_md5_hex(source)
                if md5:
                    self._remove_md5_hex(md5)
                else:
                    logger.warning(f"[VectorStoreService] 无法计算文件 MD5: {source}，跳过缓存清理")
            except Exception:
                logger.warning(f"[VectorStoreService] MD5 计算异常: {source}，跳过缓存清理")

            logger.info(f"[VectorStoreService] 已删除 {count} 条文档，来源: {source}")
            return count
        except Exception as e:
            logger.error(f"[VectorStoreService] 按来源删除失败: {e}")
            return 0

    def delete_by_ids(self, ids: list[int]) -> int:
        """按主键 ID 删除指定文档块

        注意：此操作不更新 MD5 缓存，因为按 ID 删除不一定是整个文件。

        Args:
            ids: 待删除的文档块 ID 列表

        Returns:
            删除的条目数
        """
        try:
            if not self.client.has_collection(self.collection_name):
                logger.warning(f"[VectorStoreService] 集合不存在，无法删除")
                return 0

            if not ids:
                return 0

            # 先查询确认存在
            id_strs = ", ".join(str(i) for i in ids)
            results = self.client.query(
                collection_name=self.collection_name,
                filter=f"id in [{id_strs}]",
                output_fields=["id"],
            )
            existing_count = len(results)

            if existing_count == 0:
                logger.info("[VectorStoreService] 指定 ID 均不存在")
                return 0

            # 按 ID 列表删除
            self.client.delete(
                collection_name=self.collection_name,
                filter=f"id in [{id_strs}]",
            )

            logger.info(f"[VectorStoreService] 已按 ID 删除 {existing_count} 条文档")
            return existing_count
        except Exception as e:
            logger.error(f"[VectorStoreService] 按 ID 删除失败: {e}")
            return 0

    def update_source(self, source: str) -> int:
        """更新指定来源的文档：先删除旧条目，再重新加载文件

        适用于 data/ 目录下文件内容已修改，需要刷新知识库的场景。

        Args:
            source: 文件路径（需与入库时的 source 完全一致）

        Returns:
            新插入的文档块数量，如果文件不存在或加载失败则返回 0
        """
        try:
            if not os.path.exists(source) or not os.path.isfile(source):
                logger.error(f"[VectorStoreService] 文件不存在，无法更新: {source}")
                return 0

            # 1. 删除旧条目
            deleted = self.delete_by_source(source)
            logger.info(f"[VectorStoreService] 更新文档: 已删除 {deleted} 条旧条目，来源: {source}")

            # 2. 重新加载文件
            inserted = self._insert_file(source)
            logger.info(f"[VectorStoreService] 更新文档: 已插入 {inserted} 条新条目，来源: {source}")

            return inserted
        except Exception as e:
            logger.error(f"[VectorStoreService] 更新文档失败: {e}")
            return 0

    def drop_collection(self) -> None:
        """删除集合（危险操作，仅用于重建）"""
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
            logger.info(f"[VectorStoreService] 集合 {self.collection_name} 已删除")


# python -m rag.vector_store
if __name__ == "__main__":
    vs = VectorStoreService()
    print(f"集合: {vs.collection_name}")
    print(f"文档数: {vs._get_document_count()}")

    # 列出已入库的文件
    sources = vs.get_sources()
    print(f"\n已入库文件 ({len(sources)} 个):")
    for src in sources:
        print(f"  - {src}")

    # 测试检索
    query = "开不了机"
    print(f"\n查询: {query}")
    print("=" * 50)

    print("\n[Dense 检索]")
    docs = vs.dense_search(query, k=3)
    for i, doc in enumerate(docs, 1):
        print(f"  {i}. {doc.page_content[:100]}...")

    print("\n[Sparse BM25 检索]")
    results = vs.sparse_search(query, k=3)
    for i, (doc, score) in enumerate(results, 1):
        print(f"  {i}. (score={score:.4f}) {doc.page_content[:100]}...")

    print("\n[混合检索 RRF]")
    docs = vs.hybrid_search(query, dense_k=10, sparse_k=10, rrf_k=60, final_k=3)
    for i, doc in enumerate(docs, 1):
        print(f"  {i}. {doc.page_content[:100]}...")
