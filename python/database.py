"""database.py — async Motor connection."""
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

_client: AsyncIOMotorClient | None = None

async def connect_db():
    global _client
    _client = AsyncIOMotorClient(settings.mongo_uri)
    # Ping to verify connection
    await _client.admin.command("ping")
    print("Connected to MongoDB")

async def disconnect_db():
    if _client:
        _client.close()

def get_db():
    return _client[settings.mongo_db]