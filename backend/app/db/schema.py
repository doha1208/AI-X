from sqlalchemy import Engine, inspect, text


def ensure_database_schema(engine: Engine) -> None:
    """Extend legacy SQLite tables that ``create_all`` cannot alter."""

    tables = inspect(engine).get_table_names()
    if "users" in tables:
        columns = {column["name"] for column in inspect(engine).get_columns("users")}
        if "remember_route_history" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN remember_route_history BOOLEAN NOT NULL DEFAULT 1"))
    if "score_builds" not in tables:
        return

    existing_columns = {column["name"] for column in inspect(engine).get_columns("score_builds")}
    additions = (
        ("artifact_version", "VARCHAR"),
        ("error_code", "VARCHAR"),
        ("started_at", "DATETIME"),
        ("finished_at", "DATETIME"),
    )
    with engine.begin() as connection:
        for name, ddl in additions:
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE score_builds ADD COLUMN {name} {ddl}"))
