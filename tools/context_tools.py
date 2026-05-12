"""Tools for retrieving guide, schema, and query-execution context."""

from framework.agent import Tool
from framework.context import describe_schemas, preview_query, read_guides


def get_guides(guide_names: list[str]) -> str:
    """Return the full text of one or more guide files."""
    return read_guides(guide_names)


def get_schemas(schema_names: list[str], include_row_counts: bool = False) -> str:
    """Return table and column metadata for one or more DuckDB schemas."""
    return describe_schemas(schema_names, include_row_counts=include_row_counts)


def execute_query(query: str, max_rows: int = 20) -> str:
    """Execute a SQL query preview without submitting a final answer."""
    dataframe, error, applied_max_rows = preview_query(query, max_rows=max_rows)
    if error is not None:
        return f"ERROR: {error}"
    if dataframe is None:
        return "ERROR: Query did not return a dataframe."

    return (
        "OK: query executed successfully. "
        f"Preview is limited to {applied_max_rows} row(s); run COUNT(*) separately "
        "if you need the full row count.\n\n"
        f"{dataframe}"
    )


GET_GUIDES: Tool = Tool(
    name="get_guides",
    description=(
        "Read one or more business-rule guide markdown files. Use this before "
        "writing SQL when the question contains domain terms, thresholds, "
        "exclusions, privacy rules, or other business logic. The available "
        "guide filenames are listed in the system prompt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "guide_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Guide filenames to read, e.g. ['airline_operations.md'].",
            },
        },
        "required": ["guide_names"],
    },
    function=get_guides,
)


GET_SCHEMAS: Tool = Tool(
    name="get_schemas",
    description=(
        "Return all tables, columns, and DuckDB data types for one or more "
        "schemas. Use this to verify exact schema/table/column names before "
        "writing SQL. The available schema names are listed in the system prompt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "schema_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "DuckDB schema names to inspect, e.g. ['CraftBeer'].",
            },
            "include_row_counts": {
                "type": "boolean",
                "description": "Whether to include exact row counts for each table.",
                "default": False,
            },
        },
        "required": ["schema_names"],
    },
    function=get_schemas,
)


EXECUTE_QUERY: Tool = Tool(
    name="execute_query",
    description=(
        "Run a read-only SQL query against hecks.duckdb and return a limited "
        "preview or an error. This is for exploration and validation only; it "
        "does not submit the final answer. After the final SQL has been "
        "validated, call submit_answer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "SQL query to preview. Use schema-qualified table names "
                    "such as CraftBeer.beers."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum preview rows to return, clamped to 1-50.",
                "default": 20,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["query"],
    },
    function=execute_query,
)


CONTEXT_TOOLS: tuple[Tool, ...] = (GET_GUIDES, GET_SCHEMAS, EXECUTE_QUERY)
