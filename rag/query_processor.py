"""
查询处理模块：Multi-Query 改写 + HyDE（假设性文档嵌入）

在检索前对用户查询进行增强处理，提高检索命中率：
- Multi-Query：将原始查询改写为多个不同角度的查询变体，分别检索后合并去重
- HyDE：用 LLM 生成假设性答案，将其与原始查询拼接作为检索输入

两种策略可独立开关，配置在 config/rag.yaml 的 query_processing 段。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from utils.config_handler import rag_conf
from utils.logger_handler import logger


# ============================================================================
# 提示词模板
# ============================================================================

_MULTI_QUERY_SYSTEM = """你是一个查询改写助手。你的任务是将用户关于扫地机器人/扫拖机器人的问题，
改写成 {n} 个不同角度的查询语句，用于向量检索。

严格遵循以下规则：
1. 保留原始查询的核心意图，从不同角度、不同措辞重新表述
2. 可以包含同义词替换（如"充不进电"→"充电故障"、"无法充电"、"电池不充电"）
3. 可以拆分复合问题为多个子问题
4. 可以添加相关但不过度扩展的关键词
5. 每条查询简洁明了，15-50 字
6. 输出必须是合法的 JSON 字符串数组，不包含任何其他文字

示例：
用户问题："扫地机器人开不了机怎么办"
输出：["扫地机器人无法开机解决方法", "机器人电源故障排查", "扫地机开机没反应原因"]"""

_MULTI_QUERY_USER = """用户问题：{query}

请输出 {n} 个改写后的查询，格式为 JSON 字符串数组。"""

_HYDE_SYSTEM = """你是一个扫地机器人/扫拖机器人领域的客服知识库撰写助手。
请根据用户的问题，撰写一段假设性的参考文档内容，模拟知识库中可能存在的相关条目。

规则：
1. 内容应包含具体的技术细节、常见原因和解决方案
2. 语言风格模仿产品说明书或客服FAQ
3. 长度控制在 100-300 字
4. 不要使用"假设"、"可能"等不确定措辞，要写得像真实文档
5. 直接输出文档内容，不要加任何前缀或说明"""

_HYDE_USER = """用户问题：{query}

请撰写一段与上述问题相关的假设性参考文档："""


# ============================================================================
# QueryProcessor
# ============================================================================

class QueryProcessor:
    """查询处理器：Multi-Query 改写 + HyDE

    在检索前对用户查询进行增强，提高召回率和精度。

    Attributes:
        multi_query_enabled: 是否启用 Multi-Query 改写
        n_variants: 生成的查询变体数量（含原始查询）
        hyde_enabled: 是否启用 HyDE
        max_retries: LLM 调用失败时的最大重试次数
    """

    def __init__(
        self,
        llm: BaseChatModel,
        multi_query_enabled: bool = False,
        n_variants: int = 3,
        hyde_enabled: bool = False,
        max_retries: int = 1,
    ):
        """初始化查询处理器

        Args:
            llm: 对话模型实例，用于生成改写查询和假设性文档
            multi_query_enabled: 是否启用 Multi-Query
            n_variants: Multi-Query 生成的变体数量
            hyde_enabled: 是否启用 HyDE
            max_retries: LLM 调用失败重试次数
        """
        self.llm = llm
        self.multi_query_enabled = multi_query_enabled
        self.n_variants = n_variants
        self.hyde_enabled = hyde_enabled
        self.max_retries = max_retries

        enabled_features = []
        if multi_query_enabled:
            enabled_features.append(f"Multi-Query(n={n_variants})")
        if hyde_enabled:
            enabled_features.append("HyDE")
        features_str = " + ".join(enabled_features) if enabled_features else "无"
        logger.info(f"[QueryProcessor] 初始化完成，启用的功能: {features_str}")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def process(self, query: str) -> list[str]:
        """处理查询，返回增强后的查询列表

        根据配置依次应用 HyDE 和 Multi-Query，返回用于检索的查询列表。

        Args:
            query: 原始用户查询

        Returns:
            查询字符串列表（至少包含原始查询）
        """
        # TODO：优先级 3，原始插叙和假设文档直接拼接会影响 生成多查询变体和 BM25 检索，可优化
        # Step 1: HyDE — 生成假设性文档，拼接到原始查询
        enriched_query = query
        if self.hyde_enabled:
            hyde_doc = self._generate_hypothetical_doc(query)
            if hyde_doc:
                # 拼接：原始查询 + 假设文档（用于 Dense 和 BM25 检索）
                enriched_query = f"{query}\n{hyde_doc}"
                logger.info(f"[QueryProcessor] HyDE 已生成，查询长度 {len(query)} → {len(enriched_query)}")

        # Step 2: Multi-Query — 生成多角度查询变体
        if self.multi_query_enabled:
            variants = self._rewrite_multi_query(enriched_query)
            if variants and len(variants) > 1:
                logger.info(f"[QueryProcessor] Multi-Query 生成 {len(variants)} 个查询变体")
                return variants

        return [enriched_query]

    # ------------------------------------------------------------------
    # Multi-Query 改写
    # ------------------------------------------------------------------

    def _rewrite_multi_query(self, query: str) -> list[str]:
        """调用 LLM 生成多个查询变体

        Args:
            query: 原始/增强后的查询

        Returns:
            查询变体列表，失败时返回 [原始查询]
        """
        system_msg = SystemMessage(content=_MULTI_QUERY_SYSTEM.format(n=self.n_variants))
        user_msg = HumanMessage(content=_MULTI_QUERY_USER.format(query=query, n=self.n_variants))

        for attempt in range(self.max_retries + 1):
            try:
                response = self.llm.invoke([system_msg, user_msg])
                variants = self._parse_json_array(response.content)
                if variants and len(variants) >= 1:
                    # 确保不丢失原始查询的语义，并去重
                    seen = {query}
                    unique_variants = [query]  # 原始查询始终在第一位
                    for v in variants:
                        v_clean = v.strip()
                        if v_clean and v_clean not in seen:
                            seen.add(v_clean)
                            unique_variants.append(v_clean)
                    return unique_variants
            except Exception as e:
                logger.warning(f"[QueryProcessor] Multi-Query 改写失败 (attempt {attempt+1}): {e}")

        logger.warning("[QueryProcessor] Multi-Query 改写全部失败，降级为原始查询")
        return [query]

    # ------------------------------------------------------------------
    # HyDE — 假设性文档生成
    # ------------------------------------------------------------------

    def _generate_hypothetical_doc(self, query: str) -> Optional[str]:
        """调用 LLM 生成假设性参考文档

        Args:
            query: 用户查询

        Returns:
            假设性文档文本，失败时返回 None
        """
        system_msg = SystemMessage(content=_HYDE_SYSTEM)
        user_msg = HumanMessage(content=_HYDE_USER.format(query=query))

        for attempt in range(self.max_retries + 1):
            try:
                response = self.llm.invoke([system_msg, user_msg])
                doc = response.content.strip()
                if doc and len(doc) > 20:  # 太短视为无效
                    return doc
            except Exception as e:
                logger.warning(f"[QueryProcessor] HyDE 生成失败 (attempt {attempt+1}): {e}")

        logger.warning("[QueryProcessor] HyDE 生成全部失败，将使用原始查询")
        return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_array(text: str) -> Optional[list[str]]:
        """从 LLM 输出中解析 JSON 字符串数组

        兼容 LLM 可能输出的各种格式：
        - 纯 JSON: ["a", "b"]
        - markdown 代码块: ```json [...] ```
        - 带编号: 1. "xxx" 2. "yyy"

        Args:
            text: LLM 原始输出文本

        Returns:
            解析后的字符串列表，失败返回 None
        """
        if not text:
            return None

        # 尝试 1: 直接解析 JSON
        try:
            result = json.loads(text.strip())
            if isinstance(result, list):
                return [str(item) for item in result]
        except json.JSONDecodeError:
            pass

        # 尝试 2: 从 markdown 代码块中提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                result = json.loads(json_match.group(1).strip())
                if isinstance(result, list):
                    return [str(item) for item in result]
            except json.JSONDecodeError:
                pass

        # 尝试 3: 使用正则提取所有被引号包裹的字符串
        quoted = re.findall(r'"([^"]*)"', text)
        if quoted and len(quoted) >= 1:
            return quoted

        # 尝试 4: 按行拆分，去掉编号前缀
        lines = text.strip().split("\n")
        cleaned = []
        for line in lines:
            line = re.sub(r'^[\d]+[\.\)、]\s*', '', line).strip()
            if line and len(line) > 2:
                cleaned.append(line)
        if cleaned:
            return cleaned

        return None


# ============================================================================
# 工厂函数 — 从配置创建
# ============================================================================

def create_query_processor(llm: Optional[BaseChatModel] = None) -> Optional[QueryProcessor]:
    """从 config/rag.yaml 创建 QueryProcessor 实例

    如果配置中 multi_query 和 hyde 都未启用，返回 None。

    Args:
        llm: 对话模型实例，未提供则通过模型工厂创建

    Returns:
        QueryProcessor 实例，或 None（所有功能均未启用时）
    """
    qp_conf = rag_conf.get("query_processing", {})

    mq_conf = qp_conf.get("multi_query", {})
    hyde_conf = qp_conf.get("hyde", {})

    multi_query_enabled = mq_conf.get("enabled", False)
    hyde_enabled = hyde_conf.get("enabled", False)

    if not multi_query_enabled and not hyde_enabled:
        logger.info("[QueryProcessor] 所有查询增强功能均未启用，跳过初始化")
        return None

    if llm is None:
        from model.factory import create_chat_model
        # 查询改写用低成本模型，temperature 略高以增加多样性
        llm = create_chat_model(temperature=0.3)

    return QueryProcessor(
        llm=llm,
        multi_query_enabled=multi_query_enabled,
        n_variants=mq_conf.get("n_variants", 3),
        hyde_enabled=hyde_enabled,
    )


# ============================================================================
# 文档去重工具函数
# ============================================================================

def deduplicate_documents(docs: list, by_content: bool = True) -> list:
    """对检索结果去重

    策略：先用 source+id 去重，再用内容前 80 字符去重。

    Args:
        docs: Document 列表或 (Document, score) 元组列表
        by_content: 是否启用内容去重

    Returns:
        去重后的文档列表，保持原始顺序
    """
    seen_ids = set()
    seen_prefixes = set()
    unique = []

    for item in docs:
        # 兼容裸 Document 和 (Document, score) 元组
        if isinstance(item, tuple):
            doc, _ = item
        else:
            doc = item

        # ID 去重
        doc_id = doc.metadata.get("id", id(doc))
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)

        # 内容前缀去重（前 80 字）
        # HACK: 优先级 10086，内容前缀去重机制可能存在误杀风险，目前场景无大问题
        if by_content:
            prefix = doc.page_content[:80].strip()
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)

        unique.append(item)

    return unique


# python -m rag.query_processor
if __name__ == "__main__":
    from model.factory import create_chat_model

    llm = create_chat_model(temperature=0.3)
    qp = QueryProcessor(
        llm=llm,
        multi_query_enabled=True,
        n_variants=3,
        hyde_enabled=False,
    )

    test_queries = [
        "扫地机器人充不进电是什么原因",
        "小户型适合哪些扫地机器人",
        "边刷不转了怎么修",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"原始查询: {q}")
        print(f"{'='*60}")
        variants = qp.process(q)
        for i, v in enumerate(variants, 1):
            print(f"  变体 {i}: {v}")
