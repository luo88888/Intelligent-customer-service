"""
数据库连接管理

提供 SQLAlchemy engine、session factory 以及 FastAPI 依赖注入函数。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from utils.config_handler import database_conf
from utils.logger_handler import logger

_db_cfg = database_conf.get("database", {})

DATABASE_URL = (
    f"mysql+pymysql://{_db_cfg['user']}:{_db_cfg['password']}"
    f"@{_db_cfg['host']}:{_db_cfg['port']}/{_db_cfg['database']}"
    f"?charset={_db_cfg.get('charset', 'utf8mb4')}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=_db_cfg.get("pool_size", 5),
    pool_recycle=_db_cfg.get("pool_recycle", 3600),
    echo=_db_cfg.get("echo", False),
    pool_pre_ping=True,   # 每次从池中取出连接前先 ping，避免 MySQL 超时断连
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """FastAPI 依赖注入：每个请求获取一个数据库会话，请求结束后自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有 ORM 模型对应的数据库表（在应用启动时调用）"""
    from db.base import Base
    # 确保所有模型已导入，以便 Base.metadata 能发现它们
    import db.models.user        # noqa: F401
    import db.models.conversation  # noqa: F401
    import db.models.message       # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("数据库表初始化完成")

    # 迁移：为已有数据库添加 blocks 列（如果尚不存在）
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    if "messages" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("messages")]
        if "blocks" not in columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN blocks JSON NULL "
                    "COMMENT '中间块（思考过程、工具调用、检索文档等）'"
                ))
                conn.commit()
            logger.info("已为 messages 表添加 blocks 列")
