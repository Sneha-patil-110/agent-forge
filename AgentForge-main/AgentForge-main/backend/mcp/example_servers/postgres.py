
from __future__ import annotations

import os

from fastmcp import FastMCP
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

server = FastMCP("agentforge-postgres")

_MAX_ROWS = 200
_READ_ONLY_PREFIXES = ("select", "with", "explain", "show")

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine

    if _engine is not None:
        return _engine

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not set; this server has no database to inspect.")

    _engine = create_engine(database_url, pool_pre_ping=True, future=True)
    return _engine


@server.tool
def list_schemas() -> str:
    """List every schema in the database."""

    inspector = inspect(_get_engine())
    return "\n".join(sorted(inspector.get_schema_names()))


@server.tool
def list_tables(schema: str = "public") -> str:
    """List every table in the given schema (default 'public')."""

    inspector = inspect(_get_engine())
    tables = sorted(inspector.get_table_names(schema=schema))

    if not tables:
        return f"No tables found in schema '{schema}'."

    return "\n".join(tables)


@server.tool
def describe_table(table: str, schema: str = "public") -> str:
    """Describe a table's columns, primary key, foreign keys, and indexes."""

    inspector = inspect(_get_engine())

    if table not in inspector.get_table_names(schema=schema):
        raise ValueError(f"Table '{schema}.{table}' does not exist.")

    lines = [f"Table: {schema}.{table}", "", "Columns:"]
    for column in inspector.get_columns(table, schema=schema):
        nullable = "NULL" if column["nullable"] else "NOT NULL"
        default = f" DEFAULT {column['default']}" if column.get("default") is not None else ""
        lines.append(f"  {column['name']}: {column['type']} {nullable}{default}")

    pk = inspector.get_pk_constraint(table, schema=schema)
    if pk.get("constrained_columns"):
        lines.append("")
        lines.append(f"Primary key: {', '.join(pk['constrained_columns'])}")

    fks = inspector.get_foreign_keys(table, schema=schema)
    if fks:
        lines.append("")
        lines.append("Foreign keys:")
        for fk in fks:
            referred = f"{fk.get('referred_schema') or schema}.{fk['referred_table']}"
            lines.append(f"  {', '.join(fk['constrained_columns'])} -> {referred}({', '.join(fk['referred_columns'])})")

    indexes = inspector.get_indexes(table, schema=schema)
    if indexes:
        lines.append("")
        lines.append("Indexes:")
        for index in indexes:
            unique = " UNIQUE" if index.get("unique") else ""
            lines.append(f"  {index['name']}{unique}: ({', '.join(index['column_names'])})")

    return "\n".join(lines)


@server.tool
def execute_query(sql: str, limit: int = _MAX_ROWS) -> str:
    """Execute a read-only SQL statement (SELECT/WITH/EXPLAIN/SHOW only) and return up to `limit` rows."""

    stripped = sql.strip().lower()

    if not stripped.startswith(_READ_ONLY_PREFIXES):
        raise ValueError(
            "Only read-only statements are allowed (SELECT, WITH, EXPLAIN, SHOW). "
            "This server never executes INSERT/UPDATE/DELETE/DDL."
        )

    engine = _get_engine()

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            result = connection.execute(text(sql))
            rows = result.fetchmany(limit) if result.returns_rows else []
            columns = list(result.keys()) if result.returns_rows else []
        finally:
            transaction.rollback()

    if not columns:
        return "Query executed. No rows returned."

    lines = [" | ".join(columns)]
    for row in rows:
        lines.append(" | ".join(str(value) for value in row))

    return "\n".join(lines)


if __name__ == "__main__":
    server.run()
