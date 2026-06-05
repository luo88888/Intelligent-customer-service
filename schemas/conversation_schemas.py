"""
会话相关 Pydantic 模型
"""
from datetime import datetime

from pydantic import BaseModel, Field


class ConversationListItem(BaseModel):
    """会话列表项"""
    id: int
    title: str | None
    message_count: int = Field(..., description="消息总数")
    last_message_preview: str | None = Field(None, description="最后一条消息预览")
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    conversations: list[ConversationListItem]
    total: int
    page: int
    page_size: int


class CreateConversationRequest(BaseModel):
    """创建会话请求"""
    title: str | None = Field(default=None, max_length=255, description="会话标题（可选）")


class ConversationDetailResponse(BaseModel):
    """会话详情响应"""
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
