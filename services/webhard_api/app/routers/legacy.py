from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..auth import require_api_key
from ..core import replace_public_endpoint
from ..settings import settings
from ..storage import ensure_bucket, get_client, presigned_get_url

router = APIRouter(tags=["legacy"])


@router.post("/files", dependencies=[Depends(require_api_key)])
async def legacy_upload_file(file: UploadFile = File(...)) -> dict[str, str | int]:
    client = get_client()
    ensure_bucket(client, settings.minio_webhard_bucket)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    stream = BytesIO(data)

    result = client.put_object(
        bucket_name=settings.minio_webhard_bucket,
        object_name=file.filename,
        data=stream,
        length=len(data),
        content_type=file.content_type or "application/octet-stream",
    )

    return {
        "bucket": settings.minio_webhard_bucket,
        "object_name": file.filename,
        "size": len(data),
        "etag": result.etag or "",
    }


@router.get("/files", dependencies=[Depends(require_api_key)])
async def legacy_list_files() -> dict[str, list[dict[str, str | int]]]:
    client = get_client()
    objects = client.list_objects(settings.minio_webhard_bucket, recursive=True)

    files: list[dict[str, str | int]] = []
    for obj in objects:
        files.append(
            {
                "object_name": obj.object_name,
                "size": int(obj.size or 0),
                "etag": obj.etag or "",
            }
        )

    return {"files": files}


@router.get("/files/{object_name}/download-url", dependencies=[Depends(require_api_key)])
async def legacy_get_download_url(object_name: str) -> dict[str, str]:
    url = presigned_get_url(object_name)
    return {"url": replace_public_endpoint(url)}


@router.delete("/files/{object_name}", dependencies=[Depends(require_api_key)])
async def legacy_delete_file(object_name: str) -> dict[str, str]:
    client = get_client()
    client.remove_object(settings.minio_webhard_bucket, object_name)
    return {"deleted": object_name}
