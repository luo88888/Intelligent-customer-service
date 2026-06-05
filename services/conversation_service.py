"""
会话业务逻辑层

处理会话的增删查操作。
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from db.repository.conversation_repo import ConversationRepository
from db.repository.message_repo import MessageRepository
from schemas.conversation_schemas import (
    ConversationListItem,
    ConversationListResponse,
    ConversationDetailResponse,
)
from schemas.message_schemas import MessageItem, MessageListResponse


class ConversationService:
    """会话服务"""

    def __init__(self, db: Session):
        self.conv_repo = ConversationRepository(db)
        self.msg_repo = MessageRepository(db)

    def list_conversations(self, user_id: int, page: int = 1, page_size: int = 20) -> ConversationListResponse:
        """获取用户的会话列表（分页）

        Args:
            user_id: 用户 ID
            page: 页码，从 1 开始
            page_size: 每页数量

        Returns:
            会话列表响应
        """
        conversations, total = self.conv_repo.list_by_user(user_id, page, page_size)

        items = []
        for conv in conversations:
            msg_count = self.conv_repo.get_message_count(conv.id)
            last_preview = self.conv_repo.get_last_message_preview(conv.id)
            items.append(ConversationListItem(
                id=conv.id,
                title=conv.title,
                message_count=msg_count,
                last_message_preview=last_preview,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            ))

        return ConversationListResponse(
            conversations=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def create_conversation(self, user_id: int, title: str | None = None) -> ConversationDetailResponse:
        """创建新会话

        Args:
            user_id: 用户 ID
            title: 会话标题（可选）

        Returns:
            会话详情响应
        """
        conv = self.conv_repo.create(user_id, title)
        return ConversationDetailResponse(
            id=conv.id,
            user_id=conv.user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    def get_conversation(self, conversation_id: int, user_id: int) -> ConversationDetailResponse:
        """获取会话详情（含归属校验）

        Args:
            conversation_id: 会话 ID
            user_id: 当前用户 ID

        Returns:
            会话详情响应

        Raises:
            HTTPException 404: 会话不存在或不属于当前用户
        """
        conv = self.conv_repo.get_by_id_and_user(conversation_id, user_id)
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        return ConversationDetailResponse(
            id=conv.id,
            user_id=conv.user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    def delete_conversation(self, conversation_id: int, user_id: int) -> None:
        """删除会话（含归属校验）

        Args:
            conversation_id: 会话 ID
            user_id: 当前用户 ID

        Raises:
            HTTPException 404: 会话不存在或不属于当前用户
        """
        conv = self.conv_repo.get_by_id_and_user(conversation_id, user_id)
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        self.conv_repo.delete(conv)

    def get_messages(self, conversation_id: int, user_id: int) -> MessageListResponse:
        """获取会话的全部消息（含归属校验）

        Args:
            conversation_id: 会话 ID
            user_id: 当前用户 ID

        Returns:
            消息列表响应

        Raises:
            HTTPException 404: 会话不存在或不属于当前用户
        """
        # 先校验归属
        conv = self.conv_repo.get_by_id_and_user(conversation_id, user_id)
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )

        messages = self.msg_repo.list_by_conversation(conversation_id)
        items = [
            MessageItem(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                blocks=msg.blocks,
                created_at=msg.created_at,
            )
            for msg in messages
        ]
        return MessageListResponse(
            conversation_id=conversation_id,
            messages=items,
        )
