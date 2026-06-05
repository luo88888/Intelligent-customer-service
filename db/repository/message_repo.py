"""
消息数据访问层
"""
from sqlalchemy.orm import Session

from db.models.message import Message


class MessageRepository:
    """消息数据访问"""

    def __init__(self, db: Session):
        self.db = db

    def list_by_conversation(self, conversation_id: int) -> list[Message]:
        """获取会话的全部消息，按创建时间升序"""
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .all()
        )

    def create(self, conversation_id: int, role: str, content: str,
               blocks: list[dict] | None = None) -> Message:
        """创建一条消息"""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            blocks=blocks,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def delete_by_conversation(self, conversation_id: int) -> None:
        """删除会话下的所有消息"""
        self.db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        self.db.commit()
