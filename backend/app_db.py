"""DB initialization. Picks SQLite (default) or MongoDB based on STORAGE env var."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
STORAGE = os.environ.get('STORAGE', 'sqlite').lower()

if STORAGE == 'mongo':
    from motor.motor_asyncio import AsyncIOMotorClient
    _mongo_client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = _mongo_client[os.environ['DB_NAME']]
    _sqlite_db = None
else:
    from sqlite_db import SQLiteDB
    _default_path = str(ROOT_DIR / 'ledgerly.db')
    sqlite_path = os.environ.get('SQLITE_PATH', _default_path)
    _sqlite_db = SQLiteDB(sqlite_path)
    db = _sqlite_db
    _mongo_client = None

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')


async def startup():
    if _sqlite_db is not None:
        await _sqlite_db.connect()


async def shutdown():
    if _mongo_client is not None:
        _mongo_client.close()
    if _sqlite_db is not None:
        await _sqlite_db.close()
