GROUP_INSERT = (
    "INSERT INTO groups_table(\n"
    "    owner_id,\n"
    "    name,\n"
    "    created_at\n"
    ")\n"
    "VALUES (\n"
    "    ?,\n"
    "    ?,\n"
    "    ?\n"
    ")"
)
GROUP_ADD_OWNER_MEMBER = (
    "INSERT INTO group_members(\n"
    "    group_id,\n"
    "    user_id,\n"
    "    created_at\n"
    ")\n"
    "VALUES (\n"
    "    ?,\n"
    "    ?,\n"
    "    ?\n"
    ")"
)
GROUP_SELECT_OWNER = (
    "SELECT\n"
    "    owner_id\n"
    "FROM groups_table\n"
    "WHERE id = ?"
)
GROUP_SELECT_ID_BY_OWNER_NAME = (
    "SELECT\n"
    "    id\n"
    "FROM groups_table\n"
    "WHERE owner_id = ?\n"
    "  AND name = ?"
)
GROUP_SELECT_USER_EXISTS = (
    "SELECT\n"
    "    id\n"
    "FROM users\n"
    "WHERE id = ?"
)
GROUP_ADD_MEMBER = (
    "INSERT INTO group_members(\n"
    "    group_id,\n"
    "    user_id,\n"
    "    created_at\n"
    ")\n"
    "VALUES (\n"
    "    ?,\n"
    "    ?,\n"
    "    ?\n"
    ")"
)
