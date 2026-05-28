from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers.auth import router as auth_router
from .routers.files import router as files_router
from .routers.folders import router as folders_router
from .routers.groups import router as groups_router
from .routers.legacy import router as legacy_router
from .routers.shares import router as shares_router
from .settings import settings
from .storage import ensure_bucket, get_client

app = FastAPI(title="Webhard API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(folders_router)
app.include_router(files_router)
app.include_router(shares_router)
app.include_router(groups_router)
app.include_router(legacy_router)


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    client = get_client()
    ensure_bucket(client, settings.minio_webhard_bucket)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
