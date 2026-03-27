"""Lightweight fixes when the DB was created with an older model (no Alembic)."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _ensure_identity_document_sides(engine: Engine) -> None:
    insp = inspect(engine)
    if "identity_submissions" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("identity_submissions")}
    additions: list[tuple[str, str]] = [
        ("document_front_path", "VARCHAR(512)"),
        ("document_back_path", "VARCHAR(512)"),
        ("document_front_content_type", "VARCHAR(128)"),
        ("document_back_content_type", "VARCHAR(128)"),
        ("document_front_size_bytes", "INTEGER"),
        ("document_back_size_bytes", "INTEGER"),
    ]
    with engine.begin() as conn:
        for name, sql_type in additions:
            if name not in cols:
                conn.execute(text(f"ALTER TABLE identity_submissions ADD COLUMN {name} {sql_type}"))
        if "document_path" in cols:
            conn.execute(
                text(
                    "UPDATE identity_submissions SET document_front_path = document_path "
                    "WHERE document_front_path IS NULL AND document_path IS NOT NULL"
                )
            )


def _ensure_user_dob_nationality(engine: Engine) -> None:
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "date_of_birth" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN date_of_birth DATE"))
        if "nationality" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN nationality VARCHAR(128)"))


def run_schema_fixes(engine: Engine) -> None:
    _ensure_identity_document_sides(engine)
    _ensure_user_dob_nationality(engine)
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'users'
                  AND column_name = 'monthly_income'
                """
            )
        ).fetchone()
        if row is None:
            return
        data_type = (row[0] or "").lower()
        if data_type in ("character varying", "varchar", "text", "character"):
            conn.execute(
                text(
                    """
                    ALTER TABLE users
                    ALTER COLUMN monthly_income TYPE DOUBLE PRECISION
                    USING CASE
                        WHEN monthly_income::text ~ '^-?[0-9]+(\\.[0-9]+)?([eE][-+]?[0-9]+)?$'
                        THEN monthly_income::text::double precision
                        ELSE 0.0
                    END
                    """
                )
            )
