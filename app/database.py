import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL ="postgresql+asyncpg://neondb_owner:npg_Ds7GeOJ2lruU@ep-still-fire-an80qqz5-pooler.c-6.us-east-1.aws.neon.tech/neondb?ssl=require"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    # checkfirst=True is CRITICAL. It won't overwrite your manual 'users' table,
    # but it WILL create 'news' and 'radio_favorites' if they are missing.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
