"""
Core SQLite execution engine for SQL problems.

This module is reused by every SQL problem's solution.py and wrapper.py.
It handles:
  - Parsing JSON stdin into table rows
  - Building an in-memory SQLite database from a schema spec
  - Executing a user SQL query
  - Formatting output deterministically (sorted, pipe-separated)
"""

import sqlite3
import json
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def build_connection(schema_ddl: str, table_data: dict) -> sqlite3.Connection:
    """
    Create an in-memory SQLite database, create tables per schema_ddl,
    then populate them from table_data.

    Args:
        schema_ddl: One or more CREATE TABLE statements (semicolon-separated).
        table_data: dict mapping table_name -> list of row dicts, e.g.
                    {"Employee": [{"id": 101, "name": "John", ...}, ...]}

    Returns:
        An open sqlite3.Connection (caller must close it).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Execute all DDL statements
    for statement in _split_statements(schema_ddl):
        if statement.strip():
            cursor.execute(statement)

    # Insert rows for each table
    for table_name, rows in table_data.items():
        if not rows:
            continue
        columns = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(columns)
        insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"
        for row in rows:
            values = [row.get(col) for col in columns]
            cursor.execute(insert_sql, values)

    conn.commit()
    return conn


def execute_query(conn: sqlite3.Connection, sql: str):
    """
    Execute a SELECT query and return (rows, column_names).

    Rows are plain tuples (not sqlite3.Row objects) for easy sorting.
    """
    cursor = conn.cursor()
    cursor.execute(sql.strip())
    column_names = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = [tuple(row) for row in cursor.fetchall()]
    return rows, column_names


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_rows(rows: list, sort: bool = True) -> str:
    """
    Format result rows as a string for stdout.

    - Multiple columns are separated by `|`
    - NULL becomes the literal string "NULL"
    - Rows are sorted case-insensitively for deterministic output
    """
    if sort:
        rows = sorted(rows, key=lambda r: [
            str(v).lower() if v is not None else "" for v in r
        ])

    lines = []
    for row in rows:
        parts = [str(v) if v is not None else "NULL" for v in row]
        lines.append("|".join(parts))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# stdin parsing
# ---------------------------------------------------------------------------

def parse_stdin(raw: str) -> dict:
    """
    Parse stdin into a table_data dict.

    Supports two formats:

    Format A — single table as a JSON array (list):
        [{"id": 1, "name": "Alice"}, ...]
        → {"Employee": [...]}   (table name is ignored in this case, caller handles it)

    Format B — multi-table dict:
        {"Employee": [...], "Department": [...]}

    Returns dict mapping table_name -> list of row dicts.
    """
    data = json.loads(raw.strip())
    if isinstance(data, list):
        # Caller must know the table name; we return generic key "rows"
        return {"__rows__": data}
    if isinstance(data, dict):
        return data
    raise ValueError(f"Unexpected stdin format: {type(data)}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_statements(sql_text: str) -> list:
    """Split a multi-statement SQL string on semicolons."""
    return [s.strip() for s in sql_text.split(";") if s.strip()]


# ---------------------------------------------------------------------------
# CLI: quick local smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Demo: Manager with at least 5 direct reports
    SCHEMA = """
    CREATE TABLE Employee (
        id          INTEGER,
        name        TEXT,
        department  TEXT,
        managerId   INTEGER
    )
    """

    demo_data = {
        "Employee": [
            {"id": 101, "name": "John",  "department": "A", "managerId": None},
            {"id": 102, "name": "Dan",   "department": "A", "managerId": 101},
            {"id": 103, "name": "James", "department": "A", "managerId": 101},
            {"id": 104, "name": "Amy",   "department": "A", "managerId": 101},
            {"id": 105, "name": "Anne",  "department": "A", "managerId": 101},
            {"id": 106, "name": "Ron",   "department": "B", "managerId": 101},
        ]
    }

    SOLUTION_SQL = """
    SELECT e1.name
    FROM Employee e1
    WHERE e1.id IN (
        SELECT managerId
        FROM Employee
        GROUP BY managerId
        HAVING COUNT(*) >= 5
    )
    """

    conn = build_connection(SCHEMA, demo_data)
    rows, cols = execute_query(conn, SOLUTION_SQL)
    conn.close()

    print("Columns:", cols)
    print("Result:")
    print(format_rows(rows))
    # Expected output: John
