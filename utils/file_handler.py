import hashlib
import os
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from utils.logger_handler import logger


def get_file_md5_hex(file_path: str) -> str | None:
    """获取文件的MD5哈希值

    Args:
        file_path (str): 文件路径

    Returns:
        str | None: 文件的MD5哈希值，或None（异常）
    """
    if not os.path.exists(file_path):
        logger.error(f"[md5计算]文件不存在: {file_path}")
        return None
    if not os.path.isfile(file_path):
        logger.error(f"[md5计算]路径不是文件: {file_path}")
        return None
    
    md5_obj = hashlib.md5()
    chunk_size = 4096   # 4KB分片，避免占用过多内存

    try:
        with open(file_path, "rb") as f:    # 必须以二进制模式打开
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)
    except Exception as e:
        logger.error(f"[md5计算]文件读取异常: {str(e)}")
        return None
    # 32 位十六进制字符串
    return md5_obj.hexdigest()


def listdir_with_allowed_type(folder_path: str, allowed_types: tuple[str, ...]) -> tuple[str, ...] | None:
    """返回文件夹内所有允许类型的文件
    
    Args:
        folder_path (str): 文件夹路径
        allowed_types (tuple[str, ...]): 允许的文件类型元组

    Returns:
        tuple[str, ...] | None: 允许类型文件路径元组，或None（异常）
    """
    files = []
    if not os.path.exists(folder_path):
        logger.error(f"[listdir_with_allowed_type]文件夹不存在: {folder_path}")
        return None
    if not os.path.isdir(folder_path):
        logger.error(f"[listdir_with_allowed_type]路径不是文件夹: {folder_path}")
        return None
    for file in os.listdir(folder_path):
        if any(file.endswith(ext) for ext in allowed_types):
            files.append(os.path.join(folder_path, file))
    return tuple(files)


# TODO: 提高 *_loader 函数的稳定性
def pdf_loader(file_path: str, password: str | None = None) -> list[Document] | None:
    """加载PDF文件为文档列表
    
    Args:
        file_path (str): PDF文件路径
        password (str | None, optional): PDF文件密码. 默认为 None.
    
    Returns:
        list[Document] | None: 文档列表，或None（异常）
    """
    return PyPDFLoader(file_path, password=password).load()


def txt_loader(file_path: str) -> list[Document] | None:
    """加载文本文件为文档列表
    
    Args:
        file_path (str): 文本文件路径
    
    Returns:
        list[Document] | None: 文档列表，或None（异常）
    """
    return TextLoader(file_path, autodetect_encoding=True).load()

