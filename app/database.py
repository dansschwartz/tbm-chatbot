from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Convert postgresql:// to postgresql+asyncpg:// for SQLAlchemy async
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# asyncpg uses ssl=require instead of sslmode=require
if "sslmode=require" in db_url:
    db_url = db_url.replace("sslmode=require", "ssl=require")

# Remove parameters that asyncpg doesn't support (Neon adds these)
import re
db_url = re.sub(r'[&?]channel_binding=[^&]*', '', db_url)
db_url = re.sub(r'[&?]options=[^&]*', '', db_url)

engine = create_async_engine(db_url, echo=False, pool_size=20, max_overflow=10)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
