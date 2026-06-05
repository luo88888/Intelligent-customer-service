from langchain_core.tools import tool
import random
import os
import contextvars


from rag.rag_service import RAGSummarizeService
from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


rag_service = RAGSummarizeService()

# HACK: 跨线程的潜在坑点，如果你的 Agent 在执行 RAG 检索时，使用了 loop.run_in_executor 将同步阻塞代码丢到了线程池中执行，需要注意：contextvars 默认不会自动跨越线程边界传递。如果在线程池中的代码调用了 _get_rag_cache()，可能会拿到 None 或报错。这种情况下，需要使用 contextvars.copy_context() 手动将上下文传递过去。
# 上下文隔离的 RAG 结果缓存：每个请求/Agent 执行上下文拥有独立的列表，
# 通过 ContextVar 实现，杜绝多用户并发场景下的数据交叉污染。
# 初始值为 None，由 execute_stream 在开始执行时设置为空列表。
_rag_results_ctx: contextvars.ContextVar[list[dict] | None] = \
    contextvars.ContextVar("rag_results", default=None)


def _get_rag_cache() -> list[dict]:
    """获取当前执行上下文的 RAG 结果缓存列表

    若当前上下文尚未初始化缓存，自动创建空列表并绑定到当前 ContextVar。
    """
    cache = _rag_results_ctx.get()
    if cache is None:
        cache = []
        _rag_results_ctx.set(cache)
    return cache

user_ids = ["1001", "1002", "1003", "1004", "1005", "1006"]
month_arr = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
month_arr = ["2025-" + month for month in month_arr]
external_data = {}


@tool(description="检索参考资料，以纯字符串格式返回")
def rag_summarize(query: str) -> str:
    """调用RAG服务进行摘要，同时将检索到的文档存入当前上下文缓存"""
    answer, docs = rag_service.rag_summarize_with_docs(query)
    _get_rag_cache().append({"query": query, "docs": docs})
    return answer


def drain_rag_results() -> list[dict]:
    """消费并返回当前上下文自上次 drain 以来积累的 RAG 检索结果"""
    cache = _get_rag_cache()
    results = list(cache)
    cache.clear()
    return results


# TODO: 实现获取天气的功能
@tool(description="获取指定城市的天气，以纯字符串格式返回")
def get_weather(city: str) -> str:
    """获取城市的天气"""
    return f"{city}的天气为晴天，18~25摄氏度，空气湿度为60%，南风2级，AQI为21，最近6小时无雨。"


@tool(description="获取用户所在城市的名称，以纯字符串格式返回")
def get_user_city() -> str:
    """获取用户所在城市的名称"""
    return random.choice(["北京", "上海", "广州", "深圳"])
   
   
@tool(description="获取用户ID，以纯字符串格式返回")
def get_user_id() -> str:
    """获取用户ID"""
    return random.choice(user_ids)


@tool(description="获取当前月份，以纯字符串格式返回")
def get_current_month() -> str:
    """获取当前月份"""
    return random.choice(month_arr)


def generate_external_data() -> None:
    """
    {
        "user_id": {
            "month": {"特征": xxx, "效率": xxx, ...},
            "month": {"特征": xxx, "效率": xxx, ...},
            ...
        },
        "user_id": {
            "month": {"特征": xxx, "效率": xxx, ...},
            "month": {"特征": xxx, "效率": xxx, ...},
            ...
        },
        ...
    }
    """
    if not external_data:
        data_path = get_abs_path(agent_conf["external_data_path"])
        if not os.path.exists(data_path):
            logger.error(f"外部数据文件不存在: {data_path}")
            raise FileNotFoundError(f"外部数据文件不存在: {data_path}")
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                line = line.strip()
                # "用户ID","特征","清洁效率","耗材","对比","时间"
                arr: list[str] = line.split(",")

                if len(arr) != 6:
                    logger.error(f"[generate_external_data]外部数据文件格式错误: {line}")
                    raise ValueError(f"[generate_external_data]外部数据文件格式错误: {line}")

                user_id = arr[0].replace('"', '')
                feature = arr[1].replace('"', '')
                efficiency = arr[2].replace('"', '')
                material = arr[3].replace('"', '')
                compare = arr[4].replace('"', '')
                time = arr[5].replace('"', '')
                
                if user_id not in external_data:
                    external_data[user_id] = {}
                external_data[user_id][time] = {
                    "特征": feature,
                    "效率": efficiency,
                    "耗材": material,
                    "对比": compare,
                }


# @tool(description="从外部系统获取指定用户在指定月份的使用记录，以纯字符串格式返回，如果未找到记录则返回空字符串")
def fetch_external_data(user_id: str, month: str) -> str:
    """获取指定用户的指定月份的使用记录"""
    generate_external_data()
    try:
        return external_data[user_id][month]
    except KeyError:
        logger.warning(f"[fetch_external_data]未找到用户{user_id}在月份{month}的记录")
        return ""
    

@tool(description="无入参，无返回值，调用后触发中间件自动为报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息")
def fill_context_for_report():
    """为报告生成的场景动态注入上下文信息"""
    pass





if __name__ == "__main__":
    user_id = "1005"
    month = "2025-05"
    print(fetch_external_data(user_id, month))