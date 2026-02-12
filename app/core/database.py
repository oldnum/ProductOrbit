from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

db_connection = MongoDB()

async def mongo_connect():
    if not settings.MONGODB_URL:
        raise ValueError("MONGODB_URL is not set")
    if not settings.DATABASE_NAME:
        raise ValueError("DATABASE_NAME is not set")
    
    db_connection.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_connection.db = db_connection.client[settings.DATABASE_NAME]

    await db_connection.db.products.create_index("url", unique=True)
    await db_connection.db.reviews.create_index("url", unique=True)

async def mongo_disconnect():
    db_connection.client.close()

async def mongo_check():
    if db_connection.db is None: return False

    try:
        await db_connection.db.command("ping")
        return True
    except:
        return False