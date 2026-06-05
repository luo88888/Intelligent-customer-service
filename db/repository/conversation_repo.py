"""
会话数据访问层
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from db.models.conversation import Conversation
from db.models.message import Message


class ConversationRepository:
    """会话数据访问"""

    def __init__(self, db: Session):
        self.db = db

    def list_by_user(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[Conversation], int]:
        """分页查询用户的会话列表，按更新时间降序"""
        query = (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id)
        )
        total = query.count()
        conversations = (
            query
            .order_by(desc(Conversation.updated_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return conversations, total

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def get_by_id_and_user(self, conversation_id: int, user_id: int) -> Conversation | None:
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )

    def create(self, user_id: int, title: str | None = None) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.db.delete(conversation)
        self.db.commit()

    def update_summary(self, conversation_id: int, summary_text: str, summarized_count: int) -> None:
        """更新会话的摘要状态"""
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({
            "summary_text": summary_text,
            "summarized_count": summarized_count,
        })
        self.db.commit()

    def update_title(self, conversation_id: int, title: str) -> None:
        """更新会话标题"""
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({
            "title": title,
        })
        self.db.commit()

    def get_message_count(self, conversation_id: int) -> int:
        """获取会话的消息总数"""
        return (
            self.db.query(func.count(Message.id))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        ) or 0

    def get_last_message_preview(self, conversation_id: int, max_length: int = 50) -> str | None:
        """获取会话最后一条消息的预览"""
        last_msg = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .first()
        )
        if last_msg is None:
            return None
        if len(last_msg.content) > max_length:
            return last_msg.content[:max_length] + "..."
        return last_msg.content
