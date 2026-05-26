from datetime import timedelta

from minio import Minio

from .settings import settings


def get_client() -> Minio:
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def presigned_get_url(object_name: str, expires_sec: int = 600) -> str:
    client = get_client()
    return client.presigned_get_object(
        settings.minio_webhard_bucket,
        object_name,
        expires=timedelta(seconds=expires_sec),
    )
