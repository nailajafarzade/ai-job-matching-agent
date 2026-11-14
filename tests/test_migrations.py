from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.models import Base


def test_upgrade_head_creates_current_schema(tmp_path):
    database_path = tmp_path / "migrated.db"
    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{database_path.as_posix()}",
    )

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "jobs",
        "job_analyses",
        "matches",
        "collector_runs",
        "applications",
        "application_events",
    }
    assert "apply_email" in {column["name"] for column in inspector.get_columns("jobs")}

    create_all_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(create_all_engine)
    create_all_inspector = inspect(create_all_engine)
    for table_name in Base.metadata.tables:
        migrated_columns = {
            (column["name"], str(column["type"]), column["nullable"])
            for column in inspector.get_columns(table_name)
        }
        create_all_columns = {
            (column["name"], str(column["type"]), column["nullable"])
            for column in create_all_inspector.get_columns(table_name)
        }
        assert migrated_columns == create_all_columns
        migrated_indexes = {
            (index["name"], tuple(index["column_names"]), bool(index["unique"]))
            for index in inspector.get_indexes(table_name)
        }
        create_all_indexes = {
            (index["name"], tuple(index["column_names"]), bool(index["unique"]))
            for index in create_all_inspector.get_indexes(table_name)
        }
        assert migrated_indexes == create_all_indexes
        migrated_constraints = {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints(table_name)
        }
        create_all_constraints = {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in create_all_inspector.get_unique_constraints(table_name)
        }
        assert migrated_constraints == create_all_constraints
        migrated_foreign_keys = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        create_all_foreign_keys = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in create_all_inspector.get_foreign_keys(table_name)
        }
        assert migrated_foreign_keys == create_all_foreign_keys
    create_all_engine.dispose()
    engine.dispose()
