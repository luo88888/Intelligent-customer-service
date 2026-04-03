from langchain.agents.middleware import AgentState, ModelRequest, dynamic_prompt, wrap_tool_call, before_model
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from typing import Callable, Any

from utils.logger_handler import logger
from utils.prompt_loader import load_system_prompt, load_report_prompt


@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command]
) -> ToolMessage | Command:
    """工具执行的监控"""
    logger.info(f"[monitor_tool]工具调用: {request.tool_call['name']}")
    logger.info(f"[monitor_tool]传入参数: {request.tool_call['args']}")

    try:
        result = handler(request)
        logger.info(f"[monitor_tool]工具调用成功: {request.tool_call['name']}")

        if request.tool_call['name'] == "fill_context_for_report":
            request.runtime.context["report"] = True

        return result
    except Exception as e:
        logger.error(f"[monitor_tool]工具调用失败，工具名称: {request.tool_call['name']}, 错误信息: {str(e)}")
        raise e


@before_model
def log_before_model(
    state: AgentState,  # 整个Agent的状态记录
    # HACK
    runtime: Any     # 记录了整个执行过程的上下文信息     # 记录了整个执行过程的上下文信息
):
    """模型执行前输出日志"""
    logger.info(f"[log_before_model]即将调用模型，带有{len(state['messages'])}条消息。")
    logger.debug(f"[log_before_model]最新的消息内容:[{type(state['messages'][-1]).__name__}] {state['messages'][-1].content.strip()}")

    return None


@dynamic_prompt # 每一次生成提示词之前调用
def report_prompt_switch(request: ModelRequest):
    """动态切换提示词"""
    is_report = request.runtime.context.get("report", False)
    if is_report:
        return load_report_prompt()
    return load_system_prompt()