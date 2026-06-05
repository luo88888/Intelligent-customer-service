"""
会话 ORM 模型
"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id          = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title            = Column(String(255), nullable=True, comment="对话标题，取自首条用户消息")
    summary_text     = Column(Text, nullable=True, comment="累积摘要文本（与 ConversationMemory 同步）")
    summarized_count = Column(Integer, nullable=False, default=0, comment="已摘要的消息条数")
    created_at       = Column(DateTime, nullable=False, server_default=func.now())
    updated_at       = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user     = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id}, title='{self.title}')>"
