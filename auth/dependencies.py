"""
认证依赖项

提供 FastAPI 的 Depends 函数，用于从请求中提取当前登录用户。
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models.user import User
from auth.jwt_handler import decode_access_token

# HTTP Bearer Token 安全方案
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """从请求的 Authorization 头中提取并验证 JWT，返回当前用户

    在所有需要认证的端点中作为 Depends 参数使用。

    Args:
        credentials: HTTP Bearer 凭据（由 FastAPI 自动解析）
        db: 数据库会话

    Returns:
        当前登录的 User ORM 对象

    Raises:
        HTTPException 401: Token 无效或已过期，或用户不存在
    """
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的认证令牌",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
