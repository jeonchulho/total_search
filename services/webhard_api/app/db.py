from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    UniqueConstraint,
    ForeignKey,
    create_engine,
    text,
    inspect,
)
from sqlalchemy.engine import Connection, Engine

from .settings import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None
_METADATA = MetaData()

users_table = Table(
    "users",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(255), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
)

sessions_table = Table(
    "sessions",
    _METADATA,
    Column("token", String(255), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("created_at", String(64), nullable=False),
)

folders_table = Table(
    "folders",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("path", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("owner_id", "path", name="uq_folders_owner_path"),
)

files_table = Table(
    "files",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("logical_path", Text, nullable=False),
    Column("current_version", Integer, nullable=False, server_default=text("0")),
    Column("is_deleted", Integer, nullable=False, server_default=text("0")),
    Column("deleted_at", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("owner_id", "logical_path", name="uq_files_owner_path"),
)

file_versions_table = Table(
    "file_versions",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("file_id", Integer, ForeignKey("files.id"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("object_name", Text, nullable=False),
    Column("size", Integer, nullable=False),
    Column("etag", String(255), nullable=False),
    Column("content_type", String(255), nullable=False),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("is_current", Integer, nullable=False, server_default=text("0")),
    UniqueConstraint("file_id", "version_no", name="uq_file_versions_file_version"),
)

shares_table = Table(
    "shares",
    _METADATA,
    Column("token", String(255), primary_key=True),
    Column("file_id", Integer, ForeignKey("files.id"), nullable=False),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("password_hash", Text, nullable=True),
    Column("allow_download", Integer, nullable=False, server_default=text("1")),
    Column("created_at", String(64), nullable=False),
    Column("one_time", Integer, nullable=False, server_default=text("0")),
    Column("download_count", Integer, nullable=False, server_default=text("0")),
    Column("max_downloads", Integer, nullable=True),
    Column("allow_upload", Integer, nullable=False, server_default=text("0")),
)

groups_table = Table(
    "groups_table",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("owner_id", "name", name="uq_groups_owner_name"),
)

group_members_table = Table(
    "group_members",
    _METADATA,
    Column("group_id", Integer, ForeignKey("groups_table.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("created_at", String(64), nullable=False),
)

file_permissions_table = Table(
    "file_permissions",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("file_id", Integer, ForeignKey("files.id"), nullable=False),
    Column("subject_type", String(32), nullable=False),
    Column("subject_id", Integer, nullable=True),
    Column("can_read", Integer, nullable=False, server_default=text("1")),
    Column("can_upload", Integer, nullable=False, server_default=text("0")),
    Column("can_manage", Integer, nullable=False, server_default=text("0")),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("file_id", "subject_type", "subject_id", name="uq_file_permissions_subject"),
)

folder_permissions_table = Table(
    "folder_permissions",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("folder_path", Text, nullable=False),
    Column("subject_type", String(32), nullable=False),
    Column("subject_id", Integer, nullable=True),
    Column("can_read", Integer, nullable=False, server_default=text("1")),
    Column("can_upload", Integer, nullable=False, server_default=text("0")),
    Column("can_manage", Integer, nullable=False, server_default=text("0")),
    Column("created_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("created_at", String(64), nullable=False),
    UniqueConstraint("owner_id", "folder_path", "subject_type", "subject_id", name="uq_folder_permissions_subject"),
)


class DBResult:
    def __init__(self, result: Any, lastrowid: int | None = None):
        self._result = result
        self.lastrowid = lastrowid
        try:
            self.rowcount = int(result.rowcount)
        except Exception:
            self.rowcount = 0

    def fetchone(self) -> dict[str, Any] | None:
        row = self._result.mappings().first()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._result.mappings().all()]


class DBConnection:
    def __init__(self, conn: Connection):
        self._conn = conn
        self._last_insert_id: int | None = None

    def _convert_query(self, query: str, params: tuple | list | dict | None) -> tuple[str, dict[str, Any]]:
        params = params or {}
        if isinstance(params, dict):
            return query, params

        if not isinstance(params, (tuple, list)):
            return query, {}

        parts = query.split("?")
        if len(parts) == 1:
            return query, {}

        bind: dict[str, Any] = {}
        rewritten = parts[0]
        for idx, value in enumerate(params, start=1):
            key = f"p{idx}"
            bind[key] = value
            rewritten += f":{key}"
            if idx < len(parts):
                rewritten += parts[idx]
        if len(parts) > len(params):
            rewritten += "".join(parts[len(params) + 1 :])
        return rewritten, bind

    def execute(self, query: str, params: tuple | list | dict | None = None) -> DBResult:
        normalized = query.strip().lower()
        if normalized.startswith("select last_insert_rowid"):
            return DBResult(_StaticMappingsResult([{"id": int(self._last_insert_id or 0)}]), self._last_insert_id)

        rewritten, bind = self._convert_query(query, params)
        result = self._conn.execute(text(rewritten), bind)
        try:
            self._last_insert_id = int(result.lastrowid) if result.lastrowid is not None else self._last_insert_id
        except Exception:
            pass
        return DBResult(result, self._last_insert_id)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class _StaticMappingsResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self) -> "_StaticMappingsResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


def _get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL
    current_url = settings.effective_database_url
    if _ENGINE is None or _ENGINE_URL != current_url:
        if _ENGINE is not None:
            _ENGINE.dispose()
        _ENGINE = create_engine(current_url, future=True)
        _ENGINE_URL = current_url
    return _ENGINE


def get_conn() -> DBConnection:
    engine = _get_engine()
    return DBConnection(engine.connect())


def _ensure_shares_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "shares" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("shares")}
    alter_sql: list[str] = []
    if "one_time" not in cols:
        alter_sql.append("ALTER TABLE shares ADD COLUMN one_time INTEGER NOT NULL DEFAULT 0")
    if "download_count" not in cols:
        alter_sql.append("ALTER TABLE shares ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0")
    if "max_downloads" not in cols:
        alter_sql.append("ALTER TABLE shares ADD COLUMN max_downloads INTEGER")
    if "allow_upload" not in cols:
        alter_sql.append("ALTER TABLE shares ADD COLUMN allow_upload INTEGER NOT NULL DEFAULT 0")

    if not alter_sql:
        return

    with engine.begin() as conn:
        for stmt in alter_sql:
            conn.execute(text(stmt))


def init_db() -> None:
    engine = _get_engine()
    _METADATA.create_all(engine)
    _ensure_shares_columns(engine)
