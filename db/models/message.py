"""
消息 ORM 模型
"""
from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import relationship

from db.base import Base


class Message(Base):
    __tablename__ = "messages"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, ForeignKey("conversations.id"), nullable=False)
    role            = Column(String(16), nullable=False, comment="消息角色：user 或 assistant")
    content         = Column(Text, nullable=False, comment="消息文本内容")
    blocks          = Column(JSON, nullable=True, comment="中间块的 JSON 数组（思考过程、工具调用、检索文档等）")
    created_at      = Column(DateTime, nullable=False, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', conversation_id={self.conversation_id})>"
