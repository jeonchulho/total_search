SHARE_SELECT_DOWNLOAD = (
    "SELECT\n"
    "    s.expires_at,\n"
    "    s.password_hash,\n"
    "    s.allow_download,\n"
    "    s.one_time,\n"
    "    s.download_count,\n"
    "    s.max_downloads,\n"
    "    fv.object_name\n"
    "FROM shares s\n"
    "JOIN files f ON f.id = s.file_id\n"
    "JOIN file_versions fv ON fv.file_id = f.id\n"
    "                     AND fv.is_current = 1\n"
    "WHERE s.token = ?\n"
    "  AND f.is_deleted = 0"
)
SHARE_INC_DOWNLOAD = (
    "UPDATE shares\n"
    "SET\n"
    "    download_count = download_count + 1\n"
    "WHERE token = ?"
)
SHARE_EXPIRE_NOW = (
    "UPDATE shares\n"
    "SET\n"
    "    expires_at = ?\n"
    "WHERE token = ?"
)
SHARE_SELECT_UPLOAD = (
    "SELECT\n"
    "    s.file_id,\n"
    "    s.expires_at,\n"
    "    s.password_hash,\n"
    "    s.allow_upload,\n"
    "    f.owner_id,\n"
    "    f.logical_path,\n"
    "    f.current_version,\n"
    "    f.is_deleted\n"
    "FROM shares s\n"
    "JOIN files f ON f.id = s.file_id\n"
    "WHERE s.token = ?"
)
