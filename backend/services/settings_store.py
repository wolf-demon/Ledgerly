"""Settings persistence helpers."""
from datetime import datetime, timezone

from app_db import db
from models import AppSettings

SETTINGS_ID = "default"


async def get_settings() -> AppSettings:
    doc = await db.settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        return AppSettings()
    return AppSettings(**{k: v for k, v in doc.items() if k in AppSettings.model_fields})


async def save_settings(settings: AppSettings):
    existing = await db.settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    payload = settings.model_dump()
    payload["id"] = SETTINGS_ID
    payload["created_at"] = (existing or {}).get("created_at") or datetime.now(timezone.utc).isoformat()
    if existing:
        await db.settings.update_one({"id": SETTINGS_ID}, {"$set": payload})
    else:
        await db.settings.insert_one(payload)
