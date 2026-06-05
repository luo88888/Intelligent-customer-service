"""
用户 ORM 模型
"""
from sqlalchemy import Column, BigInteger, String, DateTime, func
from sqlalchemy.orm import relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    username      = Column(String(64), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 密码哈希")
    display_name  = Column(String(128), nullable=True, comment="显示名称")
    created_at    = Column(DateTime, nullable=False, server_default=func.now())
    updated_at    = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    conversations = relationship(
        "Conversation", back_populates="user",
        cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"
