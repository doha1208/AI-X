from sqlalchemy import create_engine, inspect, text


def test_existing_score_builds_table_is_extended_for_build_lifecycle(tmp_path):
    from app.db.schema import ensure_database_schema

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE score_builds ("
                "id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL, status VARCHAR NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )

    ensure_database_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("score_builds")}
    assert {"artifact_version", "error_code", "started_at", "finished_at"} <= columns
