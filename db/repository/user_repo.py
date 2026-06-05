"""
用户数据访问层
"""
from sqlalchemy.orm import Session

from db.models.user import User


class UserRepository:
    """用户数据访问"""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, username: str) -> User | None:
        return self.db.query(User).filter(User.username == username).first()

    def create(self, username: str, password_hash: str, display_name: str | None = None) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def username_exists(self, username: str) -> bool:
        return self.db.query(User).filter(User.username == username).first() is not None
