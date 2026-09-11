"""Motor client, collection handles and index setup.

Collection handles are module-level so every other module imports the same
five names. There are exactly five collections; do not add a sixth here.
"""
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.config import settings

_client: AsyncIOMotorClient | None = None


def client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    return _client


def database() -> AsyncIOMotorDatabase:
    return client()[settings.mongo_db]


class _Collections:
    """Lazy attribute access so importing app.db never opens a socket."""

    @property
    def leads(self):
        return database()["leads"]

    @property
    def properties(self):
        return database()["properties"]

    @property
    def lead_memory(self):
        return database()["lead_memory"]

    @property
    def calls(self):
        return database()["calls"]

    @property
    def messages(self):
        return database()["messages"]


db = _Collections()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    await db.leads.create_index([("lead_id", ASCENDING)], unique=True)
    await db.leads.create_index([("lead_type", ASCENDING), ("lead_status", ASCENDING)])

    await db.properties.create_index([("property_id", ASCENDING)], unique=True)
    await db.properties.create_index([("owner_lead_id", ASCENDING)])

    await db.lead_memory.create_index([("lead_id", ASCENDING)], unique=True)

    await db.calls.create_index([("call_id", ASCENDING)], unique=True)
    await db.calls.create_index([("status", ASCENDING)])
    await db.calls.create_index([("lead_id", ASCENDING), ("started_at", DESCENDING)])

    await db.messages.create_index([("message_id", ASCENDING)], unique=True)
    await db.messages.create_index([("call_id", ASCENDING)], unique=True)
    await db.messages.create_index([("status", ASCENDING)])


async def next_id(prefix: str, collection, field: str) -> str:
    """Allocate the next sequential human-readable id, e.g. CL-0007."""
    last = await collection.find_one(sort=[(field, DESCENDING)], projection={field: 1})
    n = 0
    if last and last.get(field):
        try:
            n = int(str(last[field]).split("-")[-1])
        except ValueError:
            n = 0
    return f"{prefix}-{n + 1:04d}"
