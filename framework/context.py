"""Context discovery helpers for guides, schemas, and query previews."""

from functools import lru_cache
from pathlib import Path

import duckdb
import polars as pl

from framework.database import DATABASE_PATH

GUIDES_DIR = Path(__file__).parent.parent / "evaluation" / "data" / "guides"


def _quote_identifier(identifier: str) -> str:
    """Quote a DuckDB identifier."""
    return '"' + identifier.replace('"', '""') + '"'


@lru_cache(maxsize=1)
def list_guide_names() -> tuple[str, ...]:
    """Return available markdown guide filenames."""
    if not GUIDES_DIR.exists():
        return ()
    return tuple(sorted(path.name for path in GUIDES_DIR.glob("*.md")))


@lru_cache(maxsize=1)
def list_schema_names() -> tuple[str, ...]:
    """Return available non-system DuckDB schemas."""
    if not DATABASE_PATH.exists():
        return ()

    conn = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT table_schema
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema
            """
        ).fetchall()
        return tuple(row[0] for row in rows)
    finally:
        conn.close()


def _resolve_names(requested: list[str], available: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Resolve requested names case-insensitively against available names."""
    exact = set(available)
    by_lower = {name.lower(): name for name in available}
    resolved: list[str] = []
    missing: list[str] = []

    for raw_name in requested:
        name = raw_name.strip()
        if not name:
            continue
        if name in exact:
            resolved.append(name)
        elif name.lower() in by_lower:
            resolved.append(by_lower[name.lower()])
        else:
            missing.append(raw_name)

    return list(dict.fromkeys(resolved)), missing


def read_guides(guide_names: list[str]) -> str:
    """Read one or more guide files by filename."""
    available = list_guide_names()
    resolved, missing = _resolve_names(guide_names, available)

    parts: list[str] = []
    if missing:
        parts.append(
            "Missing guides: "
            + ", ".join(missing)
            + "\nAvailable guides: "
            + ", ".join(available)
        )

    for name in resolved:
        path = GUIDES_DIR / name
        parts.append(f"# Guide: {name}\n\n{path.read_text()}")

    if not parts:
        return "No guides returned. Available guides: " + ", ".join(available)

    return "\n\n---\n\n".join(parts)


@lru_cache(maxsize=128)
def _schema_details(schema_name: str, include_row_counts: bool) -> str:
    """Return a compact table/column summary for one schema."""
    conn = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = ? AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            [schema_name],
        ).fetchall()
        if not tables:
            return f"# Schema: {schema_name}\nNo base tables found."

        lines = [f"# Schema: {schema_name}", f"Tables: {len(tables)}"]
        for (table_name,) in tables:
            columns = conn.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                [schema_name, table_name],
            ).fetchall()
            column_text = ", ".join(
                f"{name} {data_type}{' NULL' if nullable == 'YES' else ''}"
                for name, data_type, nullable in columns
            )
            row_count_text = ""
            if include_row_counts:
                quoted_schema = _quote_identifier(schema_name)
                quoted_table = _quote_identifier(table_name)
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}"
                ).fetchone()
                count = row[0] if row is not None else "unknown"
                row_count_text = f" ({count} rows)"
            lines.append(f"- {table_name}{row_count_text}: {column_text}")

        return "\n".join(lines)
    finally:
        conn.close()


def describe_schemas(schema_names: list[str], include_row_counts: bool = False) -> str:
    """Describe all tables and columns for one or more schemas."""
    available = list_schema_names()
    resolved, missing = _resolve_names(schema_names, available)

    parts: list[str] = []
    if missing:
        parts.append(
            "Missing schemas: "
            + ", ".join(missing)
            + "\nAvailable schemas: "
            + ", ".join(available)
        )

    for schema in resolved:
        parts.append(_schema_details(schema, include_row_counts))

    if not parts:
        return "No schemas returned. Available schemas: " + ", ".join(available)

    return "\n\n---\n\n".join(parts)


def build_context_catalog() -> str:
    """Build the compact catalog shown to the agent at conversation start."""
    guide_names = list_guide_names()
    schema_names = list_schema_names()

    return (
        "Available guide files:\n"
        + ", ".join(guide_names)
        + "\n\nAvailable DuckDB schemas:\n"
        + ", ".join(schema_names)
    )


def preview_query(query: str, max_rows: int = 20) -> tuple[pl.DataFrame | None, str | None]:
    """Run a read-only preview of a SQL query with a row limit."""
    cleaned_query = query.strip().rstrip(";")
    if not cleaned_query:
        return None, "Query is empty."

    max_rows = max(1, min(max_rows, 50))
    preview_sql = f"SELECT * FROM ({cleaned_query}) AS agent_query_preview LIMIT {max_rows}"

    conn = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        result = conn.execute(preview_sql)
        return pl.DataFrame(result.fetch_arrow_table()), None
    except duckdb.Error as e:
        return None, f"DuckDB error: {e}"
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()
