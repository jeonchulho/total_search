from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from ..auth import require_bearer_user
from ..core import (
    effective_folder_permission_for_subject,
    load_owned_folders,
    load_shared_folder_permissions,
    normalize_path,
    resolve_folder_owner_for_operation,
    upsert_file_permission,
)
from ..db import get_conn, utc_now_iso
from ..schemas import CreateFolderRequest, GrantFolderPermissionRequest
from ..sql.folder_queries import (
    FOLDER_INSERT,
    FOLDER_INSERT_PERMISSION,
    FOLDER_SELECT_BY_OWNER_PATH,
    FOLDER_SELECT_FILES_FOR_APPLY,
    FOLDER_UPDATE_PERMISSION,
)

router = APIRouter(prefix="/nc/folders", tags=["folders"])


@router.post("")
async def create_folder(payload: CreateFolderRequest, user: dict = Depends(require_bearer_user)) -> dict[str, str]:
    path = normalize_path(payload.path).rstrip("/")
    conn = get_conn()
    owner_id = user["id"]
    if path:
        resolved_owner_id = resolve_folder_owner_for_operation(conn, path, user["id"], "upload")
        if resolved_owner_id is not None:
            owner_id = resolved_owner_id
    try:
        conn.execute(
            FOLDER_INSERT,
            (owner_id, path, utc_now_iso()),
        )
    except IntegrityError:
        pass
    conn.commit()
    conn.close()
    return {"path": path}


@router.post("/{folder_path:path}/share")
async def share_folder(
    folder_path: str,
    payload: GrantFolderPermissionRequest,
    user: dict = Depends(require_bearer_user),
) -> dict:
    normalized_folder = normalize_path(folder_path).rstrip("/")
    if normalized_folder != normalize_path(payload.folder_path).rstrip("/"):
        raise HTTPException(status_code=400, detail="folder_path mismatch")
    return await grant_folder_permission(payload=payload, user=user)


@router.get("/shared")
async def list_shared_folders(user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    rows = load_shared_folder_permissions(conn, user["id"])
    conn.close()
    return {"shared_folders": rows}


@router.get("/accessible")
async def list_accessible_folders(user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    owned_rows = load_owned_folders(conn, user["id"])
    shared_rows = load_shared_folder_permissions(conn, user["id"])
    conn.close()

    merged: dict[tuple[int, str], dict[str, int | str | bool]] = {}
    for row in shared_rows:
        merged[(int(row["owner_id"]), row["folder_path"])] = {
            "owner_id": int(row["owner_id"]),
            "folder_path": row["folder_path"],
            "can_read": bool(row["can_read"]),
            "can_upload": bool(row["can_upload"]),
            "can_manage": bool(row["can_manage"]),
            "source": "shared",
        }

    for row in owned_rows:
        merged[(int(row["owner_id"]), row["folder_path"])] = {
            "owner_id": int(row["owner_id"]),
            "folder_path": row["folder_path"],
            "can_read": True,
            "can_upload": True,
            "can_manage": True,
            "source": "owned",
        }

    return {"accessible_folders": list(merged.values())}


@router.post("/permissions")
async def grant_folder_permission(
    payload: GrantFolderPermissionRequest,
    user: dict = Depends(require_bearer_user),
) -> dict:
    folder_path = normalize_path(payload.folder_path).rstrip("/")
    subject_id = payload.subject_id
    if payload.subject_type == "public":
        subject_id = 0
    elif subject_id is None:
        raise HTTPException(status_code=400, detail="subject_id is required for user/group")

    conn = get_conn()
    folder = conn.execute(FOLDER_SELECT_BY_OWNER_PATH, (user["id"], folder_path)).fetchone()
    if folder is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Folder not found")

    now = utc_now_iso()
    updated = conn.execute(
        FOLDER_UPDATE_PERMISSION,
        (
            1 if payload.can_read else 0,
            1 if payload.can_upload else 0,
            1 if payload.can_manage else 0,
            user["id"],
            now,
            user["id"],
            folder_path,
            payload.subject_type,
            subject_id,
        ),
    )
    if int(updated.rowcount or 0) == 0:
        conn.execute(
            FOLDER_INSERT_PERMISSION,
            (
                user["id"],
                folder_path,
                payload.subject_type,
                subject_id,
                1 if payload.can_read else 0,
                1 if payload.can_upload else 0,
                1 if payload.can_manage else 0,
                user["id"],
                now,
            ),
        )

    affected_files = 0
    if payload.apply_existing_files:
        rows = conn.execute(
            FOLDER_SELECT_FILES_FOR_APPLY,
            (user["id"], f"{folder_path}/%"),
        ).fetchall()
        for r in rows:
            effective = effective_folder_permission_for_subject(
                conn=conn,
                owner_id=user["id"],
                logical_path=r["logical_path"],
                subject_type=payload.subject_type,
                subject_id=subject_id,
            )
            if effective is None:
                continue
            upsert_file_permission(
                conn=conn,
                file_id=int(r["id"]),
                subject_type=payload.subject_type,
                subject_id=subject_id,
                can_read=effective[0],
                can_upload=effective[1],
                can_manage=effective[2],
                created_by=user["id"],
            )
            affected_files += 1

    conn.commit()
    conn.close()

    return {
        "folder_path": folder_path,
        "subject_type": payload.subject_type,
        "subject_id": subject_id,
        "can_read": payload.can_read,
        "can_upload": payload.can_upload,
        "can_manage": payload.can_manage,
        "affected_files": affected_files,
    }
