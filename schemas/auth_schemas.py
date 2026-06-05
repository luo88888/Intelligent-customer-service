"""
认证相关 Pydantic 模型
"""
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(
        ..., min_length=3, max_length=64,
        pattern=r'^[a-zA-Z0-9_]+$',
        description="用户名，仅支持字母、数字和下划线"
    )
    password: str = Field(
        ..., min_length=6, max_length=128,
        description="密码，6-128 个字符"
    )
    display_name: str | None = Field(
        default=None, max_length=128,
        description="显示名称（可选）"
    )


class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """认证令牌响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user_id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    display_name: str | None = Field(default=None, description="显示名称")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    display_name: str | None
    created_at: str
