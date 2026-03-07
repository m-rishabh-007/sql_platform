"""
solution.py — Complete standalone solution for Judge0 execution.

This file is used by the orchestrator (orchestrator.py) to generate expected
output for every test case.  It is self-contained: no external imports beyond
the Python standard library.

stdin:  JSON array of Employee row objects
stdout: sorted, pipe-separated result rows (one per line)

Problem: Manager with at Least Five Direct Reports
"""

import sys
import json
import sqlite3

# ---------------------------------------------------------------------------
# Reference SQL solution (equivalent to solution.sql)
# ---------------------------------------------------------------------------

USER_SQL = """
SELECT e1.name
FROM Employee e1
WHERE e1.id IN (
    SELECT managerId
    FROM Employee
    GROUP BY managerId
    HAVING COUNT(*) >= 5
)
"""

# ---------------------------------------------------------------------------
# Schema & helpers (identical to wrapper.py — kept in sync manually)
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE Employee (
    id          INTEGER,
    name        TEXT,
    department  TEXT,
    managerId   INTEGER
)
"""

_INSERT_SQL = "INSERT INTO Employee VALUES (:id, :name, :department, :managerId)"


def _create_db(rows):
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(_SCHEMA_DDL)
    for row in rows:
        cursor.execute(_INSERT_SQL, row)
    conn.commit()
    return conn


def _run_query(conn, sql):
    cursor = conn.cursor()
    cursor.execute(sql.strip())
    cols = [d[0] for d in cursor.description] if cursor.description else []
    rows = [tuple(r) for r in cursor.fetchall()]
    return rows, cols


def _format_output(rows):
    rows_sorted = sorted(rows, key=lambda r: [
        str(v).lower() if v is not None else "" for v in r
    ])
    for row in rows_sorted:
        print("|".join("NULL" if v is None else str(v) for v in row))


# ---------------------------------------------------------------------------
# Main — called by Judge0 and by the orchestrator
# ---------------------------------------------------------------------------

def execute_solution():
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return

        rows = json.loads(raw)
        conn = _create_db(rows)
        result_rows, _ = _run_query(conn, USER_SQL)
        conn.close()

        _format_output(result_rows)

    except json.JSONDecodeError as e:
        print(f"Input Error: invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)
    except sqlite3.OperationalError as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Runtime Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    execute_solution()
