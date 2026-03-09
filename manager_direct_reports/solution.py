"""
solution.py -- Complete standalone solution for Judge0 execution.

Used by orchestrator_sql.py to generate expected_output for every test case.
Mirrors wrapper.py exactly -- the only difference is USER_SQL is pre-filled
with the reference solution.

Execution model: connects to mysql-eval-server, creates an ephemeral sandbox_*
database, seeds it from stdin JSON, runs USER_SQL, formats output, drops DB.

stdin:  JSON array of Employee row objects
stdout: sorted, pipe-separated result rows (one per line)

Problem: Manager with at Least Five Direct Reports
"""

import sys
import json
import uuid
import pymysql

# ---------------------------------------------------------------------------
# Reference SQL solution -- kept in sync with solution.sql
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
# MySQL connection settings -- identical to wrapper.py (keep in sync)
# ---------------------------------------------------------------------------

_MYSQL_HOST = "mysql-eval-server"
_MYSQL_USER = "judge0_runner"
_MYSQL_PASSWORD = "J0runner!secure99"

# ---------------------------------------------------------------------------
# Schema & insert logic -- identical to wrapper.py (keep in sync)
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE Employee (
    id          INT,
    name        VARCHAR(255),
    department  VARCHAR(255),
    managerId   INT
)
"""

_INSERT_SQL = """
    INSERT INTO Employee (id, name, department, managerId)
    VALUES (%s, %s, %s, %s)
"""


def _row_to_tuple(row):
    return (
        row.get("id"),
        row.get("name"),
        row.get("department"),
        row.get("managerId"),
    )


def _format_output(rows):
    rows_sorted = sorted(rows, key=lambda r: [
        str(v).lower() if v is not None else "" for v in r
    ])
    for row in rows_sorted:
        print("|".join("NULL" if v is None else str(v) for v in row))


# ---------------------------------------------------------------------------
# Main -- called by Judge0 and by the orchestrator
# ---------------------------------------------------------------------------

def execute_solution():
    if not USER_SQL.strip():
        print("Error: No SQL query provided.", file=sys.stderr)
        sys.exit(1)

    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        input_rows = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Input Error: invalid JSON -- {e}", file=sys.stderr)
        sys.exit(1)

    run_id = f"sandbox_{uuid.uuid4().hex}"

    try:
        conn = pymysql.connect(
            host=_MYSQL_HOST,
            user=_MYSQL_USER,
            password=_MYSQL_PASSWORD,
            autocommit=True,
            connect_timeout=10,
        )
    except pymysql.MySQLError as e:
        print(f"Connection Error: could not reach {_MYSQL_HOST} -- {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE `{run_id}`")
            cur.execute(f"USE `{run_id}`")
            cur.execute(_SCHEMA_DDL)
            for row in input_rows:
                cur.execute(_INSERT_SQL, _row_to_tuple(row))
            cur.execute(USER_SQL)
            result_rows = cur.fetchall()

        _format_output(result_rows)

    except pymysql.MySQLError as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Runtime Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{run_id}`")
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    execute_solution()
