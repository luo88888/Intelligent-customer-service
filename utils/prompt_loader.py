"""
提示词加载模块
"""
from utils.config_handler import prompts_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


def load_system_prompt() -> str:
    """加载系统提示词

    Returns:
        str: 系统提示词字符串
    
    Raises:
        KeyError: 如果配置文件中缺少system_prompt_path
        Exception: 如果文件读取异常
    """
    system_prompt_path = prompts_conf.get("system_prompt_path", None)
    if system_prompt_path is None:
        logger.error(f"[load_system_prompt]配置文件中缺少system_prompt_path")
        raise KeyError('Missing key "system_prompt_path"') # 提示词缺失，程序无法继续运行
    system_prompt_path = get_abs_path(system_prompt_path)
    
    try:
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except Exception as e:
        logger.error(f"[load_system_prompt]解析系统提示词异常: {str(e)}")
        raise e # 文件读取异常，程序无法继续运行
    
    return system_prompt


def load_rag_prompt() -> str:
    """加载RAG摘要提示词

    Returns:
        str: RAG摘要提示词字符串
    
    Raises:
        KeyError: 如果配置文件中缺少rag_summarize_prompt_path
        Exception: 如果文件读取异常
    """
    rag_prompt_path = prompts_conf.get("rag_summarize_prompt_path", None)
    if rag_prompt_path is None:
        logger.error(f"[load_rag_prompt]配置文件中缺少rag_summarize_prompt_path")
        raise KeyError('Missing key "rag_summarize_prompt_path"') # 提示词缺失，程序无法继续运行
    rag_prompt_path = get_abs_path(rag_prompt_path)
    
    try:
        with open(rag_prompt_path, "r", encoding="utf-8") as f:
            rag_prompt = f.read()
    except Exception as e:
        logger.error(f"[load_rag_prompt]解析RAG摘要提示词异常: {str(e)}")
        raise e # 文件读取异常，程序无法继续运行
    
    return rag_prompt


def load_report_prompt() -> str:
    """加载报告提示词

    Returns:
        str: 报告提示词字符串
    
    Raises:
        KeyError: 如果配置文件中缺少report_prompt_path
        Exception: 如果文件读取异常
    """
    report_prompt_path = prompts_conf.get("report_prompt_path", None)
    if report_prompt_path is None:
        logger.error(f"[load_report_prompt]配置文件中缺少report_prompt_path")
        raise KeyError('Missing key "report_prompt_path"') # 提示词缺失，程序无法继续运行
    report_prompt_path = get_abs_path(report_prompt_path)
    
    try:
        with open(report_prompt_path, "r", encoding="utf-8") as f:
            report_prompt = f.read()
    except Exception as e:
        logger.error(f"[load_report_prompt]解析报告提示词异常: {str(e)}")
        raise e # 文件读取异常，程序无法继续运行
    
    return report_prompt



if __name__ == '__main__':
    print("="*20, "系统提示词", "="*20)
    print(load_system_prompt())
    print("="*20, "RAG摘要提示词", "="*20)
    print(load_rag_prompt())
    print("="*20, "报告提示词", "="*20)
    print(load_report_prompt())
   