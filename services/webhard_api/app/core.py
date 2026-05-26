from datetime import datetime, timezone

from fastapi import HTTPException

from .db import utc_now_iso, get_conn
from .settings import settings
from .sql.file_queries import FILE_INSERT_PERMISSION, FILE_UPDATE_PERMISSION


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_path(path: str) -> str:
    from pathlib import PurePosixPath

    raw = path.strip().replace("\\", "/")
    normalized = str(PurePosixPath("/" + raw)).lstrip("/")
    if normalized in {"", "."}:
        raise HTTPException(status_code=400, detail="Invalid path")
    if ".." in normalized.split("/"):
        raise HTTPException(status_code=400, detail="Path traversal is not allowed")
    return normalized


def replace_public_endpoint(url: str) -> str:
    if settings.minio_endpoint in url:
        return url.replace(settings.minio_endpoint, settings.minio_public_endpoint)
    return url


def folder_ancestors(logical_path: str) -> list[str]:
    parts = logical_path.split("/")
    folder_parts = parts[:-1]
    ancestors: list[str] = []
    for i in range(1, len(folder_parts) + 1):
        ancestors.append("/".join(folder_parts[:i]))
    return ancestors


def folder_scope_paths(folder_path: str) -> list[str]:
    paths = [folder_path]
    paths.extend(folder_ancestors(f"{folder_path}/__scope__"))
    unique_paths: list[str] = []
    for path in paths:
        if path and path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def upsert_file_permission(
    conn,
    file_id: int,
    subject_type: str,
    subject_id: int,
    can_read: int,
    can_upload: int,
    can_manage: int,
    created_by: int,
) -> None:
    now = utc_now_iso()
    updated = conn.execute(
        FILE_UPDATE_PERMISSION,
        (can_read, can_upload, can_manage, created_by, now, file_id, subject_type, subject_id),
    )
    if int(updated.rowcount or 0) == 0:
        conn.execute(
            FILE_INSERT_PERMISSION,
            (file_id, subject_type, subject_id, can_read, can_upload, can_manage, created_by, now),
        )


def effective_folder_permission_for_subject(
    conn,
    owner_id: int,
    logical_path: str,
    subject_type: str,
    subject_id: int,
) -> tuple[int, int, int] | None:
    ancestors = folder_ancestors(logical_path)
    if not ancestors:
        return None

    placeholders = ",".join("?" for _ in ancestors)
    row = conn.execute(
        f"""
        SELECT can_read, can_upload, can_manage
        FROM folder_permissions
        WHERE owner_id = ?
          AND subject_type = ?
          AND subject_id = ?
          AND folder_path IN ({placeholders})
        ORDER BY LENGTH(folder_path) DESC
        LIMIT 1
        """,
        (owner_id, subject_type, subject_id, *ancestors),
    ).fetchone()
    if row is None:
        return None
    return (int(row["can_read"]), int(row["can_upload"]), int(row["can_manage"]))


def resolve_folder_owner_for_operation(conn, target_path: str, user_id: int, perm: str) -> int | None:
    col = {
        "read": "can_read",
        "upload": "can_upload",
        "manage": "can_manage",
    }.get(perm)
    if col is None:
        return None

    ancestors = folder_ancestors(target_path)
    if not ancestors:
        return None

    placeholders = ",".join("?" for _ in ancestors)
    row = conn.execute(
        f"""
        SELECT fp.owner_id
        FROM folder_permissions fp
        LEFT JOIN group_members gm
            ON gm.group_id = fp.subject_id
           AND fp.subject_type = 'group'
        WHERE fp.folder_path IN ({placeholders})
          AND fp.{col} = 1
          AND (
                (fp.subject_type = 'user' AND fp.subject_id = ?)
             OR (fp.subject_type = 'group' AND gm.user_id = ?)
             OR (fp.subject_type = 'public')
          )
        ORDER BY LENGTH(fp.folder_path) DESC, fp.owner_id ASC
        LIMIT 1
        """,
        (*ancestors, user_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return int(row["owner_id"])


def has_folder_permission(conn, owner_id: int, folder_path: str, user_id: int, perm: str) -> bool:
    col = {
        "read": "can_read",
        "upload": "can_upload",
        "manage": "can_manage",
    }.get(perm)
    if col is None:
        return False

    scope_paths = folder_scope_paths(folder_path)
    if not scope_paths:
        return False

    placeholders = ",".join("?" for _ in scope_paths)
    row = conn.execute(
        f"""
        SELECT 1
        FROM folder_permissions fp
        LEFT JOIN group_members gm
            ON gm.group_id = fp.subject_id
           AND fp.subject_type = 'group'
        WHERE fp.owner_id = ?
          AND fp.folder_path IN ({placeholders})
          AND fp.{col} = 1
          AND (
                (fp.subject_type = 'user' AND fp.subject_id = ?)
             OR (fp.subject_type = 'group' AND gm.user_id = ?)
             OR (fp.subject_type = 'public')
          )
        LIMIT 1
        """,
        (owner_id, *scope_paths, user_id, user_id),
    ).fetchone()
    return row is not None


def load_shared_folder_permissions(conn, user_id: int) -> list[dict[str, int | str]]:
    rows = conn.execute(
        """
        SELECT owner_id, folder_path,
               MAX(can_read) AS can_read,
               MAX(can_upload) AS can_upload,
               MAX(can_manage) AS can_manage
        FROM (
            SELECT fp.owner_id, fp.folder_path, fp.can_read, fp.can_upload, fp.can_manage
            FROM folder_permissions fp
            LEFT JOIN group_members gm
                ON gm.group_id = fp.subject_id
               AND fp.subject_type = 'group'
            WHERE (fp.subject_type = 'user' AND fp.subject_id = ?)
               OR (fp.subject_type = 'group' AND gm.user_id = ?)
               OR (fp.subject_type = 'public')
        )
        GROUP BY owner_id, folder_path
        ORDER BY folder_path ASC
        """,
        (user_id, user_id),
    ).fetchall()
    return [
        {
            "owner_id": int(r["owner_id"]),
            "folder_path": r["folder_path"],
            "can_read": int(r["can_read"] or 0),
            "can_upload": int(r["can_upload"] or 0),
            "can_manage": int(r["can_manage"] or 0),
        }
        for r in rows
        if int(r["can_read"] or 0) or int(r["can_upload"] or 0) or int(r["can_manage"] or 0)
    ]


def load_owned_folders(conn, user_id: int) -> list[dict[str, int | str]]:
    rows = conn.execute(
        """
        SELECT path
        FROM folders
        WHERE owner_id = ?
        ORDER BY path ASC
        """,
        (user_id,),
    ).fetchall()
    return [
        {
            "owner_id": user_id,
            "folder_path": r["path"],
            "can_read": 1,
            "can_upload": 1,
            "can_manage": 1,
        }
        for r in rows
    ]


def inherit_folder_permissions(conn, owner_id: int, logical_path: str, file_id: int, created_by: int) -> None:
    ancestors = folder_ancestors(logical_path)
    if not ancestors:
        return

    placeholders = ",".join("?" for _ in ancestors)
    rows = conn.execute(
        f"""
        SELECT folder_path, subject_type, subject_id, can_read, can_upload, can_manage
        FROM folder_permissions
        WHERE owner_id = ? AND folder_path IN ({placeholders})
        ORDER BY LENGTH(folder_path) DESC
        """,
        (owner_id, *ancestors),
    ).fetchall()

    seen_subjects: set[tuple[str, int]] = set()
    for r in rows:
        sid = int(r["subject_id"] or 0)
        key = (r["subject_type"], sid)
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        upsert_file_permission(
            conn=conn,
            file_id=file_id,
            subject_type=r["subject_type"],
            subject_id=sid,
            can_read=int(r["can_read"]),
            can_upload=int(r["can_upload"]),
            can_manage=int(r["can_manage"]),
            created_by=created_by,
        )


def is_file_owner(conn, file_id: int, user_id: int) -> bool:
    row = conn.execute("SELECT owner_id FROM files WHERE id = ?", (file_id,)).fetchone()
    return row is not None and int(row["owner_id"]) == int(user_id)


def has_file_permission(conn, file_id: int, user_id: int, perm: str) -> bool:
    if is_file_owner(conn, file_id, user_id):
        return True

    col = {
        "read": "can_read",
        "upload": "can_upload",
        "manage": "can_manage",
    }.get(perm)
    if col is None:
        return False

    user_perm = conn.execute(
        f"SELECT 1 FROM file_permissions WHERE file_id = ? AND subject_type = 'user' AND subject_id = ? AND {col} = 1",  # nosec B608
        (file_id, user_id),
    ).fetchone()
    if user_perm is not None:
        return True

    group_perm = conn.execute(
        f"""
        SELECT 1
        FROM file_permissions fp
        JOIN group_members gm ON gm.group_id = fp.subject_id
        WHERE fp.file_id = ? AND fp.subject_type = 'group' AND gm.user_id = ? AND fp.{col} = 1
        LIMIT 1
        """,  # nosec B608
        (file_id, user_id),
    ).fetchone()
    if group_perm is not None:
        return True

    public_perm = conn.execute(
        f"SELECT 1 FROM file_permissions WHERE file_id = ? AND subject_type = 'public' AND {col} = 1",  # nosec B608
        (file_id,),
    ).fetchone()
    return public_perm is not None
