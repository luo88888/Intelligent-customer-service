"""
为整个工程提供统一的绝对路径
"""
import os

def get_project_root() -> str:
    """获取项目根目录

    Returns:
        str: 项目根目录的绝对路径
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_abs_path(relative_path: str) -> str:
    """获取绝对路径

    Args:
        relative_path (str): 相对路径

    Returns:
        str: 绝对路径
    """
    return os.path.join(get_project_root(), relative_path)