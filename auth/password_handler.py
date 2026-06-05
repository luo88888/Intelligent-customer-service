"""
密码哈希处理模块

使用 bcrypt 算法对密码进行哈希和验证。
"""
import bcrypt

from utils.config_handler import database_conf

_password_conf = database_conf.get("password", {})
_bcrypt_rounds = _password_conf.get("bcrypt_rounds", 12)


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希

    Args:
        password: 明文密码

    Returns:
        bcrypt 哈希字符串
    """
    # bcrypt 要求密码不超过 72 字节
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=_bcrypt_rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否与哈希值匹配

    Args:
        plain_password: 明文密码
        hashed_password: bcrypt 哈希值

    Returns:
        是否匹配
    """
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)
