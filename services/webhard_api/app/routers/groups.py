from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from ..auth import require_bearer_user
from ..core import upsert_file_permission
from ..db import get_conn, utc_now_iso
from ..schemas import CreateGroupRequest, GrantFilePermissionRequest
from ..sql.group_queries import (
    GROUP_ADD_MEMBER,
    GROUP_ADD_OWNER_MEMBER,
    GROUP_INSERT,
    GROUP_SELECT_ID_BY_OWNER_NAME,
    GROUP_SELECT_OWNER,
    GROUP_SELECT_USER_EXISTS,
)

router = APIRouter(prefix="/nc", tags=["groups"])


@router.post("/groups")
async def create_group(payload: CreateGroupRequest, user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    try:
        conn.execute(
            GROUP_INSERT,
            (user["id"], payload.name, utc_now_iso()),
        )
        group_row = conn.execute(GROUP_SELECT_ID_BY_OWNER_NAME, (user["id"], payload.name)).fetchone()
        conn.execute(
            GROUP_ADD_OWNER_MEMBER,
            (int(group_row["id"]), user["id"], utc_now_iso()),
        )
        conn.commit()
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=400, detail="Group name already exists") from exc

    gid = int(group_row["id"])
    conn.close()
    return {"group_id": gid, "name": payload.name}


@router.post("/groups/{group_id}/members/{member_user_id}")
async def add_group_member(group_id: int, member_user_id: int, user: dict = Depends(require_bearer_user)) -> dict:
    conn = get_conn()
    group = conn.execute(GROUP_SELECT_OWNER, (group_id,)).fetchone()
    if group is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Group not found")
    if int(group["owner_id"]) != int(user["id"]):
        conn.close()
        raise HTTPException(status_code=403, detail="Group owner only")

    target = conn.execute(GROUP_SELECT_USER_EXISTS, (member_user_id,)).fetchone()
    if target is None:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    try:
        conn.execute(
            GROUP_ADD_MEMBER,
            (group_id, member_user_id, utc_now_iso()),
        )
    except IntegrityError:
        pass
    conn.commit()
    conn.close()
    return {"group_id": group_id, "member_user_id": member_user_id}


@router.post("/files/{file_id}/permissions")
async def grant_file_permission(
    file_id: int,
    payload: GrantFilePermissionRequest,
    user: dict = Depends(require_bearer_user),
) -> dict:
    from ..core import has_file_permission

    conn = get_conn()
    if not has_file_permission(conn, file_id, user["id"], "manage"):
        conn.close()
        raise HTTPException(status_code=403, detail="Manage permission denied")

    subject_id = payload.subject_id
    if payload.subject_type == "public":
        subject_id = 0
    elif subject_id is None:
        conn.close()
        raise HTTPException(status_code=400, detail="subject_id is required for user/group")

    upsert_file_permission(
        conn=conn,
        file_id=file_id,
        subject_type=payload.subject_type,
        subject_id=subject_id,
        can_read=1 if payload.can_read else 0,
        can_upload=1 if payload.can_upload else 0,
        can_manage=1 if payload.can_manage else 0,
        created_by=user["id"],
    )
    conn.commit()
    conn.close()

    return {
        "file_id": file_id,
        "subject_type": payload.subject_type,
        "subject_id": subject_id,
        "can_read": payload.can_read,
        "can_upload": payload.can_upload,
        "can_manage": payload.can_manage,
    }
