"""
wrapper.py -- Platform injection template for: Manager with at Least Five Direct Reports

Execution model (MySQL via ephemeral sandbox schema):
  1. The contestant writes a SQL query in the editor (template.sql is the starter).
  2. The platform injects that SQL as USER_SQL = \"\"\"<contestant's SQL>\"\"\".
  3. The combined Python file is submitted to Judge0 as Python (language_id: 71).
  4. The wrapper connects to mysql-eval-server (internal Docker network),
     creates a temporary sandbox_<uuid> database, seeds it from stdin JSON,
     runs USER_SQL, formats the result, then DROPS the sandbox database.

stdin format:
  JSON array, one object per employee row:
  [{"id": 101, "name": "John", "department": "A", "managerId": null}, ...]

stdout format:
  One result row per line; multiple columns pipe-separated (|).
  Rows are sorted lexicographically (case-insensitive) for deterministic grading.
  SQL NULL values are printed as the literal string NULL.

Infrastructure requirements:
  - Judge0 worker image must have pymysql installed (see Dockerfile.worker).
  - ENABLE_NETWORK=true must be set in judge0.conf.
  - mysql-eval-server must be running and reachable on the internal Docker network.
"""

import sys
import json
import uuid
import pymysql

# ===== PLATFORM INJECTION POINT =====
# The contestant's SQL query will be injected here as:
#   USER_SQL = \"\"\"SELECT ... FROM ...\"\"\"
# DO NOT MODIFY THIS LINE OR THE BLOCK BELOW.
USER_SQL = ""
# ===== END INJECTION POINT =====

# ---------------------------------------------------------------------------
# MySQL connection settings (internal Docker network -- not exposed to host)
# ---------------------------------------------------------------------------
# !!  judge0_runner has GRANT ALL only on sandbox_% databases.
#     It cannot touch any other database or escalate privileges.
# !!  Change this password to match mysql/init.sql before production use.

_MYSQL_HOST = "mysql-eval-server"
_MYSQL_USER = "judge0_runner"
_MYSQL_PASSWORD = "J0runner!secure99"

# ---------------------------------------------------------------------------
# Schema & insert logic (update both wrapper.py and solution.py together)
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE Employee (
    id          INT,
    name        VARCHAR(255),
    department  VARCHAR(255),
    managerId   INT
)
"""

# PyMySQL uses %s positional placeholders (not SQLite's :name syntax)
_INSERT_SQL = """
    INSERT INTO Employee (id, name, department, managerId)
    VALUES (%s, %s, %s, %s)
"""


def _row_to_tuple(row):
    """Map a JSON dict row to the positional tuple required by _INSERT_SQL."""
    return (
        row.get("id"),
        row.get("name"),
        row.get("department"),
        row.get("managerId"),
    )


def _format_output(rows):
    """Sort deterministically (case-insensitive) and print pipe-separated rows."""
    rows_sorted = sorted(rows, key=lambda r: [
        str(v).lower() if v is not None else "" for v in r
    ])
    for row in rows_sorted:
        # pymysql returns Python None for SQL NULL -- identical to sqlite3 behaviour
        print("|".join("NULL" if v is None else str(v) for v in row))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute_solution():
    if not USER_SQL.strip():
        print("Error: No SQL query provided.", file=sys.stderr)
        sys.exit(1)

    raw = sys.stdin.read().strip()
    if not raw:
        return  # empty test -> empty output

    try:
        input_rows = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Input Error: invalid JSON -- {e}", file=sys.stderr)
        sys.exit(1)

    # Each submission gets its own schema -- zero collision with concurrent runs
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
            # 1. Provision ephemeral schema
            cur.execute(f"CREATE DATABASE `{run_id}`")
            cur.execute(f"USE `{run_id}`")
            cur.execute(_SCHEMA_DDL)

            # 2. Seed test-case data from stdin
            for row in input_rows:
                cur.execute(_INSERT_SQL, _row_to_tuple(row))

            # 3. Execute contestant SQL
            cur.execute(USER_SQL)

            # 4. Capture results (cursor.description available immediately after execute)
            cols = [d[0] for d in cur.description] if cur.description else []
            result_rows = cur.fetchall()

        _format_output(result_rows)

    except pymysql.MySQLError as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Runtime Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # CRITICAL: always drop the sandbox -- even if the query raised an exception
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{run_id}`")
        except Exception:
            pass  # best-effort cleanup
        conn.close()


if __name__ == "__main__":
    execute_solution()
