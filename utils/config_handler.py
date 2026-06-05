"""
配置处理模块
"""
import yaml

from utils.path_tool import get_abs_path


# TODO: 提高安全性，将 yaml.load 替换为 yaml.safe_load

def load_rag_config(config_path: str=get_abs_path("config/rag.yaml"), encoding: str="utf-8") -> dict:
    """加载rag配置文件

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/rag.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 配置字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config


def load_chroma_config(config_path: str=get_abs_path("config/chroma.yaml"), encoding: str="utf-8") -> dict:
    """加载chroma配置文件

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/chroma.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 配置字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config


def load_prompts_config(config_path: str=get_abs_path("config/prompts.yaml"), encoding: str="utf-8") -> dict:
    """加载prompts配置文件

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/prompts.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 配置字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config


def load_agent_config(config_path: str=get_abs_path("config/agent.yaml"), encoding: str="utf-8") -> dict:
    """加载agent配置文件

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/agent.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 配置字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config


def load_memory_config(config_path: str=get_abs_path("config/agent.yaml"), encoding: str="utf-8") -> dict:
    """加载记忆模块配置（从 agent.yaml 的 memory 节）

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/agent.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 记忆配置字典，若配置文件中无 memory 节则返回空字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config.get("memory", {})


def load_database_config(config_path: str=get_abs_path("config/database.yaml"), encoding: str="utf-8") -> dict:
    """加载数据库配置文件

    Args:
        config_path (str, optional): 配置文件路径. 默认为 get_abs_path("config/database.yaml").
        encoding (str, optional): 编码. 默认为 "utf-8".

    Returns:
        dict: 配置字典
    """
    with open(config_path, "r", encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config


rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()
agent_conf = load_agent_config()
memory_conf = load_memory_config()
database_conf = load_database_config()


if __name__ == "__main__":
    print(rag_conf)
    print(chroma_conf)
    print(prompts_conf)
    print(agent_conf)
    print(type(agent_conf)) # dict