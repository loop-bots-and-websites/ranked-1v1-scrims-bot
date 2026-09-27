import os
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.errors import PyMongoError

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB", "rankbot")

_client: Optional[AsyncMongoClient] = None
_database = None

players = None
matches = None
scrims = None
mod_actions = None
counters = None


def _require_db():
    if _database is None:
        raise RuntimeError("MongoDB is not initialized. Call await db.init_db() first.")


def _now():
    return datetime.now(timezone.utc)


def _normalise_player(doc: Optional[dict], user_id: int) -> dict:
    if doc is None:
        return {
            "user_id": int(user_id),
            "elo": 0,
            "rank": "Unranked",
            "subrank": "",
            "wins": 0,
            "losses": 0,
            "in_queue": False,
            "queue_since": None,
        }

    doc.pop("_id", None)
    doc.setdefault("user_id", int(user_id))
    doc.setdefault("elo", 0)
    doc.setdefault("rank", "Unranked")
    doc.setdefault("subrank", "")
    doc.setdefault("wins", 0)
    doc.setdefault("losses", 0)
    doc.setdefault("in_queue", False)
    doc.setdefault("queue_since", None)
    return doc


async def init_db():
    """Connect to MongoDB Atlas and create the indexes used by the bot."""
    global _client, _database, players, matches, scrims, mod_actions, counters

    if not MONGODB_URI:
        raise RuntimeError(
            "MONGODB_URI is missing. Add your MongoDB Atlas connection string "
            "to the hosting provider's environment variables."
        )

    if _client is not None:
        return

    try:
        _client = AsyncMongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
        await _client.admin.command("ping")

        _database = _client[DB_NAME]
        players = _database["players"]
        matches = _database["matches"]
        scrims = _database["scrims"]
        mod_actions = _database["mod_actions"]
        counters = _database["counters"]

        await players.create_index("user_id", unique=True)
        await players.create_index([("in_queue", 1), ("elo", 1), ("queue_since", 1)])

        await matches.create_index("match_id", unique=True)
        await matches.create_index("thread_id", unique=True)
        await matches.create_index("status")

        await scrims.create_index("scrim_id", unique=True)
        await scrims.create_index("message_id")
        await scrims.create_index("thread_id")
        await scrims.create_index("status")

        await mod_actions.create_index([("guild_id", 1), ("created_at", -1)])

        print(f"MongoDB connected: {DB_NAME}")

    except PyMongoError:
        if _client is not None:
            await _client.close()
        _client = None
        _database = None
        raise


async def close_db():
    global _client, _database, players, matches, scrims, mod_actions, counters
    if _client is not None:
        await _client.close()
    _client = None
    _database = None
    players = matches = scrims = mod_actions = counters = None


async def _next_id(counter_name: str) -> int:
    _require_db()
    doc = await counters.find_one_and_update(
        {"_id": counter_name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["value"])


# ---------- PLAYERS ----------

async def get_player(user_id: int) -> dict:
    _require_db()
    user_id = int(user_id)

    doc = await players.find_one({"user_id": user_id})
    if doc is None:
        doc = {
            "user_id": user_id,
            "elo": 0,
            "rank": "Unranked",
            "subrank": "",
            "wins": 0,
            "losses": 0,
            "in_queue": False,
            "queue_since": None,
            "created_at": _now(),
        }
        try:
            await players.insert_one(doc)
        except Exception:
            # Another request may have created the same player concurrently.
            doc = await players.find_one({"user_id": user_id})

    return _normalise_player(doc, user_id)


async def update_player(user_id: int, **fields):
    _require_db()
    user_id = int(user_id)
    fields.pop("_id", None)
    fields["updated_at"] = _now()
    defaults = {
        "user_id": user_id,
        "elo": 0,
        "rank": "Unranked",
        "subrank": "",
        "wins": 0,
        "losses": 0,
        "in_queue": False,
        "queue_since": None,
        "created_at": _now(),
    }

    # Filter out any field being explicitly set in $set so MongoDB never throws a path conflict
    set_on_insert = {k: v for k, v in defaults.items() if k not in fields}

    await players.update_one(
        {"user_id": user_id},
        {
            "$set": fields,
            "$setOnInsert": set_on_insert,
        },
        upsert=True,
    )


async def set_queue_state(user_id: int, in_queue: bool):
    _require_db()
    user_id = int(user_id)

    update = {
        "in_queue": bool(in_queue),
        "queue_since": _now() if in_queue else None,
        "updated_at": _now(),
    }

    await players.update_one(
        {"user_id": user_id},
        {
            "$set": update,
            "$setOnInsert": {
                "user_id": user_id,
                "elo": 0,
                "rank": "Unranked",
                "subrank": "",
                "wins": 0,
                "losses": 0,
                "created_at": _now(),
            },
        },
        upsert=True,
    )


async def get_queued_players() -> list[dict]:
    _require_db()
    cursor = players.find({"in_queue": True}).sort("queue_since", 1)
    return [doc for doc in await cursor.to_list(length=None)]



async def create_match(thread_id: int, player1: int, player2: int) -> int:
    _require_db()
    match_id = await _next_id("matches")

    await matches.insert_one({
        "match_id": match_id,
        "thread_id": int(thread_id),
        "player1": int(player1),
        "player2": int(player2),
        "winner": None,
        "loser": None,
        "winner_points": None,
        "loser_points": None,
        "submitted_by": None,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
    })
    return match_id


async def get_match(match_id: int) -> Optional[dict]:
    _require_db()
    doc = await matches.find_one({"match_id": int(match_id)})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_match(match_id: int, **fields):
    _require_db()
    fields.pop("_id", None)
    fields["updated_at"] = _now()
    await matches.update_one(
        {"match_id": int(match_id)},
        {"$set": fields},
    )


async def get_active_matches() -> list[dict]:
    _require_db()
    cursor = matches.find({"status": {"$in": ["pending", "awaiting_confirm"]}})
    rows = await cursor.to_list(length=None)
    for row in rows:
        row.pop("_id", None)
    return rows


# ---------- SCRIMS ----------

def joined_list(scrim: dict) -> list[int]:
    value = scrim.get("joined_players", [])

    if isinstance(value, list):
        return [int(x) for x in value]

    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except (ValueError, TypeError):
            pass

    return []


async def create_scrim(
    host_id: int,
    message_id: int,
    thread_id: int,
    channel_id: int,
    format_type: str,
    region: str,
    teams: str,
    map_type: str,
    match_type: str,
    server_link: str,
    minimum_rank: str = "",
    max_rank: str = "",
    max_players: int = 14,
    joined_players=None,
    status: str = "open",
) -> int:
    _require_db()
    scrim_id = await _next_id("scrims")

    if joined_players is None:
        joined = []
    elif isinstance(joined_players, list):
        joined = [int(x) for x in joined_players]
    else:
        joined = joined_list({"joined_players": joined_players})

    await scrims.insert_one({
        "scrim_id": scrim_id,
        "host_id": int(host_id),
        "message_id": int(message_id),
        "thread_id": int(thread_id),
        "channel_id": int(channel_id),
        "format_type": format_type,
        "region": region,
        "teams": teams,
        "map_type": map_type,
        "match_type": match_type,
        "server_link": server_link,
        "minimum_rank": minimum_rank,
        "max_rank": max_rank,
        "max_players": int(max_players),
        "joined_players": joined,
        "status": status,
        "created_at": _now(),
        "updated_at": _now(),
    })
    return scrim_id


async def get_scrim(scrim_id: int) -> Optional[dict]:
    _require_db()
    doc = await scrims.find_one({"scrim_id": int(scrim_id)})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_scrim(scrim_id: int, **fields):
    _require_db()
    fields.pop("_id", None)

    if "joined_players" in fields:
        fields["joined_players"] = joined_list({"joined_players": fields["joined_players"]})

    fields["updated_at"] = _now()

    await scrims.update_one(
        {"scrim_id": int(scrim_id)},
        {"$set": fields},
    )


async def get_open_scrims() -> list[dict]:
    _require_db()
    cursor = scrims.find({"status": "open"})
    rows = await cursor.to_list(length=None)
    for row in rows:
        row.pop("_id", None)
    return rows



async def log_mod_action(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    action: str,
    reason: str,
):
    _require_db()

    await mod_actions.insert_one({
        "guild_id": int(guild_id),
        "user_id": int(user_id),
        "moderator_id": int(moderator_id),
        "action": action,
        "reason": reason,
        "created_at": _now(),
    })
