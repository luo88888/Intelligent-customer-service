"""
消息相关 Pydantic 模型
"""
from datetime import datetime

from pydantic import BaseModel, Field


class MessageItem(BaseModel):
    """单条消息"""
    id: int
    role: str = Field(..., description="消息角色：user 或 assistant")
    content: str
    blocks: list[dict] | None = Field(None, description="中间块列表（思考过程、工具调用、检索文档等）")
    created_at: datetime


class MessageListResponse(BaseModel):
    """消息列表响应"""
    conversation_id: int
    messages: list[MessageItem]


class MessageSendRequest(BaseModel):
    """发送消息请求"""
    content: str = Field(..., min_length=1, description="用户发送的消息文本")


class MessageSendResponse(BaseModel):
    """发送消息响应（非流式）"""
    message_id: int
    role: str = "assistant"
    content: str
    blocks: list[dict] | None = None
    rag_docs: list[dict] | None = None
    created_at: datetime
