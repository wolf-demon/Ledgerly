"""
Minimal Motor-compatible async SQLite layer for Ledgerly.

Goal: keep server.py almost unchanged when swapping MongoDB -> SQLite.

Design:
- 4 known tables (projects, categories, transactions, rules) with explicit columns
  for fields we filter/sort by, plus a `data` JSON column for the rest.
- A `Collection` class exposes the subset of Motor methods used in server.py:
    insert_one, find_one, find (with sort + to_list), update_one, update_many,
    delete_one, delete_many, aggregate (limited to the year-extract pipeline).
- All methods are async. Filters support equality, $regex (prefix only),
  $in, and None-equality. Sort supports a single field with direction.
"""
from __future__ import annotations

import json
import re as _re
from typing import Any, Dict, List, Optional, Iterable

import aiosqlite


# Table definitions: column name -> (sql type, key in document)
# Special key '__data__' means "the rest of the document is JSON-stored here".
_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "projects": {
        "columns": [
            ("id", "TEXT PRIMARY KEY"),
            ("created_at", "TEXT NOT NULL"),
            ("data", "TEXT NOT NULL"),
        ],
        "indexed_fields": {"id", "created_at"},
    },
    "categories": {
        "columns": [
            ("id", "TEXT PRIMARY KEY"),
            ("project_id", "TEXT NOT NULL"),
            ("created_at", "TEXT NOT NULL"),
            ("data", "TEXT NOT NULL"),
        ],
        "indexed_fields": {"id", "project_id", "created_at"},
        "indexes": [("project_id",)],
    },
    "transactions": {
        "columns": [
            ("id", "TEXT PRIMARY KEY"),
            ("project_id", "TEXT NOT NULL"),
            ("date", "TEXT NOT NULL"),
            ("description", "TEXT NOT NULL"),
            ("amount", "REAL NOT NULL"),
            ("category_id", "TEXT"),
            ("created_at", "TEXT NOT NULL"),
            ("data", "TEXT NOT NULL"),
        ],
        "indexed_fields": {
            "id", "project_id", "date", "description", "amount", "category_id", "created_at",
        },
        "indexes": [("project_id", "date"), ("category_id",)],
    },
    "rules": {
        "columns": [
            ("id", "TEXT PRIMARY KEY"),
            ("project_id", "TEXT NOT NULL"),
            ("pattern", "TEXT NOT NULL"),
            ("category_id", "TEXT NOT NULL"),
            ("created_at", "TEXT NOT NULL"),
            ("data", "TEXT NOT NULL"),
        ],
        "indexed_fields": {"id", "project_id", "pattern", "category_id", "created_at"},
        "indexes": [("project_id", "pattern")],
    },
}


def _build_where(spec: Dict[str, Any], indexed: set) -> tuple[str, list]:
    """Translate a Mongo-style filter dict into SQL WHERE + params.

    Supports:
      - equality: {"id": "x"}
      - $in: {"id": {"$in": [...]}}
      - $regex prefix anchor: {"date": {"$regex": "^2025"}}
      - explicit None: {"category_id": None}  (IS NULL)
    """
    if not spec:
        return "", []
    parts: list = []
    params: list = []
    for k, v in spec.items():
        if k not in indexed:
            # Not an indexed column — fallback to JSON LIKE search (rare in our usage)
            parts.append("json_extract(data, ?) = ?")
            params.append(f"$.{k}")
            params.append(v)
            continue
        if v is None:
            parts.append(f"{k} IS NULL")
        elif isinstance(v, dict):
            if "$in" in v:
                vals = list(v["$in"])
                if not vals:
                    parts.append("0")  # always false
                else:
                    placeholders = ",".join(["?"] * len(vals))
                    parts.append(f"{k} IN ({placeholders})")
                    params.extend(vals)
            elif "$regex" in v:
                pat = v["$regex"]
                if pat.startswith("^"):
                    parts.append(f"{k} LIKE ?")
                    params.append(pat[1:].replace("%", r"\%") + "%")
                else:
                    # generic regex: load via REGEXP function below
                    parts.append(f"{k} REGEXP ?")
                    params.append(pat)
            elif "$exists" in v:
                if v["$exists"]:
                    parts.append(f"{k} IS NOT NULL")
                else:
                    parts.append(f"{k} IS NULL")
            else:
                # fall back to equality with json
                parts.append(f"{k} = ?")
                params.append(v)
        else:
            parts.append(f"{k} = ?")
            params.append(v)
    return " AND ".join(parts), params


def _row_to_doc(row: aiosqlite.Row, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct a document from a row: data JSON + indexed cols overlay."""
    data = json.loads(row["data"])
    # Indexed columns are authoritative
    for col, _ in schema["columns"]:
        if col == "data":
            continue
        if col in data:
            data[col] = row[col]
        elif row[col] is not None:
            data[col] = row[col]
    return data


class _Cursor:
    """Imitates motor.motor_asyncio.AsyncIOMotorCursor for the methods we use."""

    def __init__(self, collection: "Collection", spec: Dict[str, Any]):
        self._coll = collection
        self._spec = spec
        self._sort: Optional[tuple[str, int]] = None
        self._limit: Optional[int] = None

    def sort(self, field: str, direction: int = 1) -> "_Cursor":
        self._sort = (field, direction)
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        return await self._coll._fetch(self._spec, sort=self._sort, limit=length)

    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        rows = await self.to_list(self._limit)
        for r in rows:
            yield r


class Collection:
    def __init__(self, db: "SQLiteDB", name: str):
        self.db = db
        self.name = name
        self.schema = _SCHEMAS[name]
        self.indexed: set = set(self.schema["indexed_fields"])

    def _split(self, doc: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
        cols: Dict[str, Any] = {}
        for col, _ in self.schema["columns"]:
            if col == "data":
                continue
            cols[col] = doc.get(col)
        data_json = json.dumps({k: v for k, v in doc.items() if k != "_id"})
        return cols, data_json

    async def insert_one(self, doc: Dict[str, Any]):
        cols, data_json = self._split(doc)
        col_names = [c for c, _ in self.schema["columns"]]
        values = [cols.get(c) if c != "data" else data_json for c in col_names]
        placeholders = ",".join(["?"] * len(col_names))
        sql = f"INSERT INTO {self.name} ({','.join(col_names)}) VALUES ({placeholders})"
        async with self.db._lock:
            async with self.db._conn.execute(sql, values):
                pass
            await self.db._conn.commit()
        return type("InsertResult", (), {"inserted_id": doc.get("id")})()

    async def find_one(self, spec: Dict[str, Any], projection: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        rows = await self._fetch(spec, limit=1)
        return rows[0] if rows else None

    def find(self, spec: Optional[Dict[str, Any]] = None, projection: Optional[Dict] = None) -> _Cursor:
        return _Cursor(self, spec or {})

    async def _fetch(self, spec: Dict[str, Any], sort: Optional[tuple] = None,
                      limit: Optional[int] = None) -> List[Dict[str, Any]]:
        where, params = _build_where(spec, self.indexed)
        sql = f"SELECT * FROM {self.name}"
        if where:
            sql += f" WHERE {where}"
        if sort:
            field, direction = sort
            if field in self.indexed:
                sql += f" ORDER BY {field} {'ASC' if direction == 1 else 'DESC'}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        async with self.db._lock:
            cur = await self.db._conn.execute(sql, params)
            cur.row_factory = aiosqlite.Row
            rows = await cur.fetchall()
            await cur.close()
        return [_row_to_doc(r, self.schema) for r in rows]

    async def update_one(self, spec: Dict[str, Any], update: Dict[str, Any]):
        await self._do_update(spec, update, multi=False)
        return type("R", (), {"modified_count": 1})()

    async def update_many(self, spec: Dict[str, Any], update: Dict[str, Any]):
        n = await self._do_update(spec, update, multi=True)
        return type("R", (), {"modified_count": n})()

    async def _do_update(self, spec: Dict[str, Any], update: Dict[str, Any], multi: bool) -> int:
        if "$set" not in update:
            return 0
        set_dict = update["$set"]
        rows = await self._fetch(spec, limit=None if multi else 1)
        for r in rows:
            r.update(set_dict)
            cols, data_json = self._split(r)
            col_names = [c for c, _ in self.schema["columns"]]
            assignments = []
            params: list = []
            for c in col_names:
                if c == "data":
                    assignments.append("data = ?")
                    params.append(data_json)
                else:
                    assignments.append(f"{c} = ?")
                    params.append(cols.get(c))
            params.append(r["id"])
            sql = f"UPDATE {self.name} SET {', '.join(assignments)} WHERE id = ?"
            async with self.db._lock:
                await self.db._conn.execute(sql, params)
        async with self.db._lock:
            await self.db._conn.commit()
        return len(rows)

    async def delete_one(self, spec: Dict[str, Any]):
        return await self._do_delete(spec, multi=False)

    async def delete_many(self, spec: Dict[str, Any]):
        return await self._do_delete(spec, multi=True)

    async def _do_delete(self, spec: Dict[str, Any], multi: bool):
        where, params = _build_where(spec, self.indexed)
        sql = f"DELETE FROM {self.name}"
        if where:
            sql += f" WHERE {where}"
        if not multi:
            sql += " LIMIT 1"
        async with self.db._lock:
            try:
                cur = await self.db._conn.execute(sql, params)
            except aiosqlite.OperationalError:
                # SQLite was not built with ENABLE_UPDATE_DELETE_LIMIT — strip LIMIT
                if not multi and sql.endswith(" LIMIT 1"):
                    sql = sql[: -len(" LIMIT 1")]
                    rows = await self._fetch(spec, limit=1)
                    if rows:
                        cur = await self.db._conn.execute(
                            f"DELETE FROM {self.name} WHERE id = ?", (rows[0]["id"],)
                        )
                    else:
                        return type("R", (), {"deleted_count": 0})()
                else:
                    raise
            count = cur.rowcount
            await cur.close()
            await self.db._conn.commit()
        return type("R", (), {"deleted_count": count})()

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> "_AggCursor":
        return _AggCursor(self, pipeline)


class _AggCursor:
    """Supports only the year-extract pipeline used by analytics_years:
       [{$match: {project_id: x}}, {$group: {_id: {$substr: [$date, 0, 4]}}}, {$sort: {_id: -1}}]
    """

    def __init__(self, coll: Collection, pipeline: List[Dict[str, Any]]):
        self.coll = coll
        self.pipeline = pipeline

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        match = {}
        for stage in self.pipeline:
            if "$match" in stage:
                match = stage["$match"]
                break
        where, params = _build_where(match, self.coll.indexed)
        sql = (
            f"SELECT DISTINCT substr(date, 1, 4) AS y FROM {self.coll.name}"
        )
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY y DESC"
        async with self.coll.db._lock:
            cur = await self.coll.db._conn.execute(sql, params)
            cur.row_factory = aiosqlite.Row
            rows = await cur.fetchall()
            await cur.close()
        for r in rows:
            yield {"_id": r["y"]}


class SQLiteDB:
    """Acts like a Motor database — `db.projects`, `db.transactions` return Collection."""

    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        import asyncio
        self._lock = asyncio.Lock()
        self._collections: Dict[str, Collection] = {}

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        # Register a REGEXP helper so non-prefix regex still works
        await self._conn.create_function(
            "REGEXP", 2, lambda pat, val: 1 if val and _re.search(pat, val) else 0
        )
        for table, schema in _SCHEMAS.items():
            cols_sql = ", ".join(f"{name} {coltype}" for name, coltype in schema["columns"])
            await self._conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols_sql})")
            for idx in schema.get("indexes", []):
                idx_name = f"idx_{table}_{'_'.join(idx)}"
                await self._conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({', '.join(idx)})"
                )
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    def __getattr__(self, name: str) -> Collection:
        if name in _SCHEMAS:
            if name not in self._collections:
                self._collections[name] = Collection(self, name)
            return self._collections[name]
        raise AttributeError(name)

    def __getitem__(self, name: str) -> Collection:
        return self.__getattr__(name)
