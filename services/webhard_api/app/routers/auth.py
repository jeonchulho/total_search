from fastapi import APIRouter, HTTPException

from ..auth import create_session, hash_password, verify_password
from ..db import get_conn, utc_now_iso
from ..schemas import LoginRequest, RegisterRequest
from ..sql.auth_queries import AUTH_INSERT_USER, AUTH_SELECT_USER_BY_USERNAME

router = APIRouter(prefix="/nc/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterRequest) -> dict[str, str | int]:
    conn = get_conn()
    try:
        conn.execute(
            AUTH_INSERT_USER,
            (payload.username, hash_password(payload.password), utc_now_iso()),
        )
        conn.commit()
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists") from exc

    inserted = conn.execute(AUTH_SELECT_USER_BY_USERNAME, (payload.username,)).fetchone()
    conn.close()
    return {"user_id": int(inserted["id"]), "username": payload.username}


@router.post("/login")
async def login(payload: LoginRequest) -> dict[str, str]:
    conn = get_conn()
    row = conn.execute(
        AUTH_SELECT_USER_BY_USERNAME,
        (payload.username,),
    ).fetchone()
    conn.close()

    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, expires_at = create_session(int(row["id"]))
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "username": row["username"],
    }
