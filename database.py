from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "sqlite+aiosqlite:///./recipes.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_models():
    from models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
