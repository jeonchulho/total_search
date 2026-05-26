from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class CreateFolderRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)


class CreateShareRequest(BaseModel):
    expires_in_sec: int = Field(default=3600, ge=60, le=60 * 60 * 24 * 30)
    password: str | None = Field(default=None, min_length=4, max_length=128)
    allow_download: bool = True
    allow_upload: bool = False
    one_time: bool = False
    max_downloads: int | None = Field(default=None, ge=1, le=100000)


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)


class GrantFilePermissionRequest(BaseModel):
    subject_type: str = Field(pattern="^(user|group|public)$")
    subject_id: int | None = None
    can_read: bool = True
    can_upload: bool = False
    can_manage: bool = False


class GrantFolderPermissionRequest(BaseModel):
    folder_path: str = Field(min_length=1, max_length=1024)
    subject_type: str = Field(pattern="^(user|group|public)$")
    subject_id: int | None = None
    can_read: bool = True
    can_upload: bool = False
    can_manage: bool = False
    apply_existing_files: bool = False
