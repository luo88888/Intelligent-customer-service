"""
JWT 令牌处理模块

负责创建和验证 JWT 访问令牌。
"""
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from utils.config_handler import database_conf

_jwt_conf = database_conf.get("jwt", {})

SECRET_KEY = _jwt_conf.get("secret_key", "change-me")
ALGORITHM = _jwt_conf.get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = _jwt_conf.get("access_token_expire_minutes", 1440)


def create_access_token(user_id: int, username: str) -> str:
    """为用户创建 JWT 访问令牌

    Args:
        user_id: 用户 ID
        username: 用户名

    Returns:
        JWT 令牌字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解码并验证 JWT 令牌

    Args:
        token: JWT 令牌字符串

    Returns:
        解码后的 payload 字典，验证失败返回 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
