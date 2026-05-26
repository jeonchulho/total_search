from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..auth import verify_password
from ..core import now_utc, replace_public_endpoint
from ..db import get_conn, utc_now_iso
from ..settings import settings
from ..storage import ensure_bucket, get_client, presigned_get_url
from ..sql.file_queries import (
    FILE_INSERT_VERSION,
    FILE_RESET_CURRENT_VERSION,
    FILE_UPDATE_VERSION_COUNTER,
)
from ..sql.share_queries import (
    SHARE_EXPIRE_NOW,
    SHARE_INC_DOWNLOAD,
    SHARE_SELECT_DOWNLOAD,
    SHARE_SELECT_UPLOAD,
)
router = APIRouter(prefix="/nc/shares", tags=["shares"])


@router.get("/{share_token}/download-url")
async def shared_download_url(share_token: str, password: str | None = None) -> dict[str, str]:
    conn = get_conn()
    row = conn.execute(
        SHARE_SELECT_DOWNLOAD,
        (share_token,),
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Share not found")

    if datetime.fromisoformat(row["expires_at"]) < now_utc():
        raise HTTPException(status_code=410, detail="Share expired")

    if int(row["allow_download"] or 0) == 0:
        raise HTTPException(status_code=403, detail="Share download is disabled")

    if row["password_hash"] and (not password or not verify_password(password, row["password_hash"])):
        raise HTTPException(status_code=401, detail="Share password required")

    download_count = int(row["download_count"] or 0)
    max_downloads = row["max_downloads"]
    if max_downloads is not None and download_count >= int(max_downloads):
        raise HTTPException(status_code=410, detail="Share max downloads exceeded")

    conn = get_conn()
    conn.execute(SHARE_INC_DOWNLOAD, (share_token,))
    if int(row["one_time"] or 0) == 1:
        conn.execute(SHARE_EXPIRE_NOW, (utc_now_iso(), share_token))
    conn.commit()
    conn.close()

    return {"url": replace_public_endpoint(presigned_get_url(row["object_name"]))}


@router.post("/{share_token}/upload-version")
async def shared_upload_version(
    share_token: str,
    file: UploadFile = File(...),
    password: str | None = None,
) -> dict[str, int | str]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    conn = get_conn()
    row = conn.execute(
        SHARE_SELECT_UPLOAD,
        (share_token,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Share not found")
    if datetime.fromisoformat(row["expires_at"]) < now_utc():
        conn.close()
        raise HTTPException(status_code=410, detail="Share expired")
    if row["password_hash"] and (not password or not verify_password(password, row["password_hash"])):
        conn.close()
        raise HTTPException(status_code=401, detail="Share password required")
    if int(row["allow_upload"] or 0) == 0:
        conn.close()
        raise HTTPException(status_code=403, detail="Share upload is disabled")
    if int(row["is_deleted"] or 0) == 1:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")

    owner_id = int(row["owner_id"])
    file_id = int(row["file_id"])
    logical_path = row["logical_path"]
    version_no = int(row["current_version"]) + 1
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
            owner_id,
            now_iso,
        ),
    )
    conn.execute(FILE_UPDATE_VERSION_COUNTER, (version_no, now_iso, file_id))
    conn.commit()
    conn.close()

    return {"file_id": file_id, "version_no": version_no, "size": len(content), "etag": result.etag or ""}
