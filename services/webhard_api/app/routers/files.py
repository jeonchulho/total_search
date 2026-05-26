from datetime import timedelta
from io import BytesIO
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..auth import require_bearer_user
from ..core import (
    has_file_permission,
    has_folder_permission,
    inherit_folder_permissions,
    now_utc,
    normalize_path,
    replace_public_endpoint,
    resolve_folder_owner_for_operation,
)
from ..db import get_conn, utc_now_iso
from ..schemas import CreateShareRequest
from ..settings import settings
from ..storage import ensure_bucket, get_client, presigned_get_url
from ..sql.file_queries import (
    FILE_EXISTS_BY_ID,
    FILE_INSERT,
    FILE_INSERT_SHARE,
    FILE_INSERT_VERSION,
    FILE_LIST_ACTIVE,
    FILE_LIST_INCLUDE_DELETED,
    FILE_LIST_SHARED,
    FILE_LIST_TRASH,
    FILE_RESTORE,
    FILE_RESET_CURRENT_VERSION,
    FILE_SELECT_BY_OWNER_PATH,
    FILE_SELECT_CURRENT_OBJECT,
    FILE_SELECT_DELETED_FLAG,
    FILE_SELECT_META_BY_ID,
    FILE_SELECT_VERSIONS,
    FILE_TRASH,
    FILE_UPDATE_AFTER_UPLOAD,
    FILE_UPDATE_VERSION_COUNTER,
)

router = APIRouter(prefix="/nc/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    path: str = Query(..., description="Logical path including file name, e.g. docs/policy.pdf"),
    file: UploadFile = File(...),
    user: dict = Depends(require_bearer_user),
) -> dict[str, str | int]:
    logical_path = normalize_path(path)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    conn = get_conn()
    owner_id = user["id"]
    row = conn.execute(
        FILE_SELECT_BY_OWNER_PATH,
        (owner_id, logical_path),
    ).fetchone()
    if row is None:
        resolved_owner_id = resolve_folder_owner_for_operation(conn, logical_path, user["id"], "upload")
        if resolved_owner_id is not None:
            owner_id = resolved_owner_id
            row = conn.execute(
                FILE_SELECT_BY_OWNER_PATH,
                (owner_id, logical_path),
            ).fetchone()

    now_iso = utc_now_iso()
    if row is None:
        conn.execute(
            FILE_INSERT,
            (owner_id, logical_path, now_iso, now_iso),
        )
        inserted = conn.execute(FILE_SELECT_BY_OWNER_PATH, (owner_id, logical_path)).fetchone()
        file_id = int(inserted["id"])
        current_version = 0
        inherit_folder_permissions(conn, owner_id=owner_id, logical_path=logical_path, file_id=file_id, created_by=user["id"])
    else:
        file_id = int(row["id"])
        current_version = int(row["current_version"])

    version_no = current_version + 1
    stamp = now_utc().strftime("%Y%m%d%H%M%S")
    object_name = f"user-{owner_id}/{logical_path}.v{version_no}.{stamp}"

    client = get_client()
    ensure_bucket(client, settings.minio_webhard_bucket)
    result = client.put_object(
        bucket_name=settings.minio_webhard_bucket,
        object_name=object_name,
        data=BytesIO(content),
        length=len(content),
        content_type=file.content_type or "application/octet-stream",
    )

    conn.execute(FILE_RESET_CURRENT_VERSION, (file_id,))
    conn.execute(
        FILE_INSERT_VERSION,
        (
            file_id,
            version_no,
            object_name,
            len(content),
            result.etag or "",
            file.content_type or "application/octet-stream",
            user["id"],
            now_iso,
        ),
    )
    conn.execute(
        FILE_UPDATE_AFTER_UPLOAD,
        (version_no, now_iso, file_id),
    )
    conn.commit()
    conn.close()

    return {
        "file_id": file_id,
        "logical_path": logical_path,
        "version_no": version_no,
        "size": len(content),
        "etag": result.etag or "",
    }


@router.post("/{file_id}/upload-version")
async def upload_new_version(
    file_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(require_bearer_user),
) -> dict[str, str | int]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    conn = get_conn()
    file_row = conn.execute(
        FILE_SELECT_META_BY_ID,
        (file_id,),
    ).fetchone()
    if file_row is None or int(file_row["is_deleted"]) == 1:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
    if not has_file_permission(conn, file_id, user["id"], "upload"):
        conn.close()
        raise HTTPException(status_code=403, detail="Upload permission denied")

    logical_path = file_row["logical_path"]
    version_no = int(file_row["current_version"]) + 1
    stamp = now_utc().strftime("%Y%m%d%H%M%S")
    object_name = f"user-{file_row['owner_id']}/{logical_path}.v{version_no}.{stamp}"

    client = get_client()
    ensure_bucket(client, settings.minio_webhard_bucket)
    result = client.put_object(
        bucket_name=settings.minio_webhard_bucket,
        object_name=object_name,
        data=BytesIO(content),
        length=len(content),
        content_type=file.content_type or "application/octet-stream",
    )

    now_iso = utc_now_iso()
    conn.execute(FILE_RESET_CURRENT_VERSION, (file_id,))
    conn.execute(
        FILE_INSERT_VERSION,
        (
            file_id,
            version_no,
            object_name,
            len(content),
            result.etag or "",
            file.content_type or "application/octet-stream",
            user["id"],
            now_iso,
        ),
    )
    conn.execute(FILE_UPDATE_VERSION_COUNTER, (version_no, now_iso, file_id))
    conn.commit()
    conn.close()

    return {"file_id": file_id, "version_no": version_no, "size": len(content), "etag": result.etag or ""}


@router.get("")
async def list_files(
    prefix: str = "",
    include_deleted: bool = False,
    owner_id: int | None = None,
    user: dict = Depends(require_bearer_user),
) -> dict:
    prefix_norm = normalize_path(prefix) if prefix else ""
    conn = get_conn()
    visible_owner_id = user["id"] if owner_id is None else owner_id
    if visible_owner_id != user["id"]:
        if not prefix_norm:
            conn.close()
            raise HTTPException(status_code=400, detail="prefix is required for shared folder listing")
        if not has_folder_permission(conn, visible_owner_id, prefix_norm, user["id"], "read"):
            conn.close()
            raise HTTPException(status_code=403, detail="Folder read permission denied")

    if include_deleted:
        rows = conn.execute(
            FILE_LIST_INCLUDE_DELETED,
            (visible_owner_id, f"{prefix_norm}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            FILE_LIST_ACTIVE,
            (visible_owner_id, f"{prefix_norm}%"),
        ).fetchall()
    conn.close()

    return {
        "files": [
            {
                "file_id": int(r["id"]),
                "logical_path": r["logical_path"],
                "current_version": int(r["current_version"]),
                "is_deleted": bool(r["is_deleted"]),
                "deleted_at": r["deleted_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    }


@router.get("/shared")
async def list_shared_files(user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    rows = conn.execute(
        FILE_LIST_SHARED,
        (user["id"], user["id"], user["id"]),
    ).fetchall()
    conn.close()

    return {
        "shared_files": [
            {
                "file_id": int(r["id"]),
                "logical_path": r["logical_path"],
                "current_version": int(r["current_version"]),
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    }


@router.get("/{file_id}/versions")
async def list_versions(file_id: int, user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    exists = conn.execute(FILE_EXISTS_BY_ID, (file_id,)).fetchone()
    if exists is None:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
    if not has_file_permission(conn, file_id, user["id"], "read"):
        conn.close()
        raise HTTPException(status_code=403, detail="Read permission denied")

    rows = conn.execute(
        FILE_SELECT_VERSIONS,
        (file_id,),
    ).fetchall()
    conn.close()

    return {
        "versions": [
            {
                "version_id": int(r["id"]),
                "version_no": int(r["version_no"]),
                "object_name": r["object_name"],
                "size": int(r["size"]),
                "etag": r["etag"],
                "content_type": r["content_type"],
                "created_at": r["created_at"],
                "is_current": bool(r["is_current"]),
            }
            for r in rows
        ]
    }


@router.get("/{file_id}/download-url")
async def get_download_url(file_id: int, user: dict = Depends(require_bearer_user)) -> dict[str, str]:
    conn = get_conn()
    if not has_file_permission(conn, file_id, user["id"], "read"):
        conn.close()
        raise HTTPException(status_code=403, detail="Read permission denied")
    row = conn.execute(
        FILE_SELECT_CURRENT_OBJECT,
        (file_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")

    return {"url": replace_public_endpoint(presigned_get_url(row["object_name"]))}


@router.post("/{file_id}/trash")
async def move_to_trash(file_id: int, user: dict = Depends(require_bearer_user)) -> dict[str, int | str]:
    conn = get_conn()
    row = conn.execute(FILE_EXISTS_BY_ID, (file_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
    if not has_file_permission(conn, file_id, user["id"], "manage"):
        conn.close()
        raise HTTPException(status_code=403, detail="Manage permission denied")

    conn.execute(
        FILE_TRASH,
        (utc_now_iso(), utc_now_iso(), file_id),
    )
    conn.commit()
    conn.close()
    return {"file_id": file_id, "status": "trashed"}


@router.get("/trash")
async def list_trash(user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    rows = conn.execute(
        FILE_LIST_TRASH,
        (user["id"],),
    ).fetchall()
    conn.close()

    return {
        "trash": [
            {
                "file_id": int(r["id"]),
                "logical_path": r["logical_path"],
                "deleted_at": r["deleted_at"],
            }
            for r in rows
        ]
    }


@router.post("/{file_id}/restore")
async def restore_file(file_id: int, user: dict = Depends(require_bearer_user)) -> dict[str, int | str]:
    conn = get_conn()
    row = conn.execute(FILE_EXISTS_BY_ID, (file_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
    if not has_file_permission(conn, file_id, user["id"], "manage"):
        conn.close()
        raise HTTPException(status_code=403, detail="Manage permission denied")

    conn.execute(
        FILE_RESTORE,
        (utc_now_iso(), file_id),
    )
    conn.commit()
    conn.close()
    return {"file_id": file_id, "status": "restored"}


@router.post("/{file_id}/share")
async def create_share(file_id: int, payload: CreateShareRequest, user: dict = Depends(require_bearer_user)) -> dict:
    from ..auth import hash_password

    conn = get_conn()
    row = conn.execute(FILE_SELECT_DELETED_FLAG, (file_id,)).fetchone()
    if row is None or int(row["is_deleted"]) == 1:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
    if not has_file_permission(conn, file_id, user["id"], "manage"):
        conn.close()
        raise HTTPException(status_code=403, detail="Manage permission denied")

    token = secrets.token_urlsafe(24)
    expires_at = (now_utc() + timedelta(seconds=payload.expires_in_sec)).isoformat()
    password_hash = hash_password(payload.password) if payload.password else None

    conn.execute(
        FILE_INSERT_SHARE,
        (
            token,
            file_id,
            user["id"],
            expires_at,
            password_hash,
            1 if payload.allow_download else 0,
            utc_now_iso(),
            1 if payload.one_time else 0,
            payload.max_downloads,
            1 if payload.allow_upload else 0,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "share_token": token,
        "expires_at": expires_at,
        "share_url": f"/nc/shares/{token}/download-url",
        "password_protected": payload.password is not None,
        "allow_download": payload.allow_download,
        "allow_upload": payload.allow_upload,
        "one_time": payload.one_time,
        "max_downloads": payload.max_downloads,
    }
