AUTH_INSERT_USER = (
    "INSERT INTO users(\n"
    "    username,\n"
    "    password_hash,\n"
    "    created_at\n"
    ")\n"
    "VALUES (\n"
    "    ?,\n"
    "    ?,\n"
    "    ?\n"
    ")"
)
AUTH_SELECT_USER_BY_USERNAME = (
    "SELECT\n"
    "    id,\n"
    "    username,\n"
    "    password_hash\n"
    "FROM users\n"
    "WHERE username = ?"
)
