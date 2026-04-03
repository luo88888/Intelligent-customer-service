"""
日志处理模块
"""
import logging
import os
from datetime import datetime

from utils.path_tool import get_abs_path



# 日志保存的根目录
LOG_ROOT = get_abs_path("logs")

# 确保日志根目录存在
os.makedirs(LOG_ROOT, exist_ok=True)

# 日志格式配置 error info debug
DEFAULT_LOG_FORMAT = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)


def get_logger(
    name: str="agent",
    console_level: int=logging.INFO,
    file_level: int=logging.DEBUG,
    log_file=None
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(console_handler)

    # 创建文件处理器
    if not log_file:
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    
    logger.addHandler(file_handler)

    return logger


# 快捷获取日志记录器
logger = get_logger()   # 日志记录器


if __name__ == "__main__":
    logger.debug("这是一条debug日志")
    logger.info("这是一条info日志")
    logger.warning("这是一条warning日志")
    logger.error("这是一条error日志")
    logger.critical("这是一条critical日志")