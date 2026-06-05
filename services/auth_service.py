"""
认证业务逻辑层

处理用户注册和登录。
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from db.repository.user_repo import UserRepository
from auth.password_handler import hash_password, verify_password
from auth.jwt_handler import create_access_token
from schemas.auth_schemas import TokenResponse


class AuthService:
    """认证服务"""

    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def register(self, username: str, password: str, display_name: str | None = None) -> TokenResponse:
        """用户注册

        Args:
            username: 用户名
            password: 明文密码
            display_name: 显示名称（可选）

        Returns:
            TokenResponse: 包含 JWT 令牌的响应

        Raises:
            HTTPException 409: 用户名已存在
        """
        if self.user_repo.username_exists(username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        password_hash = hash_password(password)
        user = self.user_repo.create(username, password_hash, display_name)

        access_token = create_access_token(user.id, user.username)
        return TokenResponse(
            access_token=access_token,
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
        )

    def login(self, username: str, password: str) -> TokenResponse:
        """用户登录

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            TokenResponse: 包含 JWT 令牌的响应

        Raises:
            HTTPException 401: 用户名或密码错误
        """
        user = self.user_repo.get_by_username(username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        access_token = create_access_token(user.id, user.username)
        return TokenResponse(
            access_token=access_token,
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
        )
