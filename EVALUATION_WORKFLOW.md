# SQL Platform — Evaluation Workflow

This document explains the complete lifecycle of a SQL submission: from the moment a
user submits their query to the final verdict of pass or fail.

---

## High-Level Overview

```
User writes SQL
      │
      ▼
Platform injects SQL into wrapper.py
      │
      ▼
Combined Python file submitted to Judge0 (language_id: 71, enable_network: true)
      │
      ▼
Judge0 sandbox executes the Python file
      │
      ├── connects to mysql-eval-server (internal Docker network)
      ├── creates ephemeral sandbox_<uuid> database
      ├── seeds it with test case rows from stdin
      ├── runs USER_SQL (the contestant's query)
      └── prints sorted output to stdout
      │
      ▼
Judge0 returns stdout to platform
      │
      ▼
Platform compares stdout vs expected_output from testcases JSON
      │
      ▼
Verdict: Accepted / Wrong Answer / Runtime Error / Time Limit Exceeded
```

---

## Phase 1 — Test Suite Generation (done once by problem setter)

Before the contest, `orchestrator_sql.py` pre-generates all test cases and stores
expected outputs. This runs **once** when the problem is being set up.

### Steps

1. **Load files** from the problem directory:
   - `wrapper.py` — execution template with `USER_SQL = ""`
   - `solution.sql` — the correct reference SQL
   - `config.json` — how many cases of each type to generate
   - `examples.json` — 2–3 visible example cases

2. **SQL injection** — orchestrator replaces the placeholder in wrapper.py:
   ```
   Before:  USER_SQL = ""
   After:   USER_SQL = """
            SELECT name FROM Employee WHERE ...
            """
   ```

3. **For each test case** (visible examples + generated cases):
   - Run `generator.py <rule_type>` to produce a JSON stdin (the dataset)
   - POST the injected Python + JSON stdin to Judge0 at `localhost:3000`
   - Judge0 runs the solution against the seeded MySQL database
   - The stdout returned is stored as `expected_output`

4. **Write** `<problem_name>_sql_testcases.json` — this file contains every test
   case with its `stdin` and `expected_output`.

```
orchestrator_sql.py
      │
      ├── wrapper.py  ──┐
      ├── solution.sql ─┼──► inject_sql_into_wrapper() ──► master_source (Python)
      │                 ┘
      ├── generator.py ──► stdin JSON (per test case)
      │
      └── Judge0 POST (master_source + stdin) ──► stdout = expected_output
                                                       │
                                                       ▼
                                              testcases.json saved to disk
```

---

## Phase 2 — Contest Submission (happens every time a user submits)

When a contestant submits their SQL query during the contest:

### Step 1 — SQL Injection

The platform takes the contestant's raw SQL string and injects it into `wrapper.py`
using the same anchor string:

```python
injected_code = wrapper_code.replace(
    'USER_SQL = ""',
    f'USER_SQL = """\n{contestant_sql.strip()}\n"""'
)
```

The result is a complete, self-contained Python file with the user's SQL embedded inside.

### Step 2 — Submission to Judge0

The injected Python is POSTed to Judge0 for each test case:

```http
POST http://localhost:3000/submissions?base64_encoded=false&wait=true
Content-Type: application/json

{
  "source_code": "<injected Python>",
  "language_id": 71,
  "stdin": "<JSON test case rows>",
  "enable_network": true
}
```

`enable_network: true` is mandatory — without it the Docker sandbox cannot reach
`mysql-eval-server` and the connection fails silently.

### Step 3 — Execution inside Judge0 Sandbox

Inside the isolated sandbox, the Python wrapper does the following in sequence:

```
1. Read stdin        →  parse JSON array/dict into Python list of row dicts

2. Connect           →  pymysql.connect(host="mysql-eval-server", ...)
                        TCP connection over internal Docker network

3. Create database   →  CREATE DATABASE sandbox_<uuid>
                        UUID ensures zero collision with concurrent submissions

4. Create table      →  run _SCHEMA_DDL  (e.g. CREATE TABLE Employee ...)

5. Insert rows       →  for each row in stdin:
                            INSERT INTO Employee VALUES (%s, %s, %s, %s)

6. Run user SQL      →  cur.execute(USER_SQL)
                        This is the contestant's actual query

7. Fetch results     →  cur.fetchall()

8. Format output     →  sort rows lexicographically (case-insensitive)
                        print each row as pipe-separated values
                        Python None → printed as the literal string "NULL"

9. Cleanup           →  DROP DATABASE sandbox_<uuid>   ← always runs, even on error
                        conn.close()
```

### Step 4 — Judge0 Returns Result

Judge0 returns a JSON response with:

| Field    | Meaning |
|----------|---------|
| `stdout` | Everything printed to stdout by the wrapper |
| `stderr` | Any Python/MySQL error messages |
| `status` | Status object with `id` and `description` |
| `time`   | Execution time in seconds |
| `memory` | Memory used in KB |

Key status codes:

| id | Meaning |
|----|---------|
| 3  | Accepted — ran successfully |
| 5  | Time Limit Exceeded |
| 6  | Compilation Error (Python syntax error) |
| 11 | Runtime Error (NZEC) — Python raised an exception |
| 13 | Internal Error — Judge0 infrastructure problem |

### Step 5 — Grading

The platform compares:

```
contestant_output = result["stdout"].strip()
expected_output   = testcases[i]["expected_output"].strip()

verdict = "Accepted" if contestant_output == expected_output else "Wrong Answer"
```

Since output is **always sorted** by the wrapper (not by SQL ORDER BY), two queries
that produce the same logical rows in different orders will still match.

---

## Why Output Is Always Sorted

SQL does not guarantee row order without an explicit ORDER BY. Even with ORDER BY,
different MySQL versions or execution plans can return rows in different sequences.
To make grading deterministic, the wrapper sorts all output in Python:

```python
rows_sorted = sorted(rows, key=lambda r: [
    str(v).lower() if v is not None else "" for v in r
])
```

This means ORDER BY in the contestant's SQL has **no effect** on whether they pass
or fail. Only the set of rows matters.

---

## Data Flow Diagram (Contest Submission)

```
Contestant's SQL (string)
          │
          ▼
  wrapper.py template
  USER_SQL = ""  ──replace──►  USER_SQL = """<sql>"""
          │
          ▼
  injected_code (Python string, ASCII-only)
          │
          │           stdin: JSON test case
          ▼                       │
  Judge0 POST ◄───────────────────┘
  localhost:3000
          │
          ▼
  Docker sandbox (isolate)
  Python 3 runtime
          │
          ▼
  pymysql TCP ──► mysql-eval-server container
                        │
                        ├── CREATE DATABASE sandbox_<uuid>
                        ├── CREATE TABLE ...
                        ├── INSERT rows from stdin
                        ├── EXECUTE USER_SQL
                        ├── FETCH rows
                        └── DROP DATABASE sandbox_<uuid>
          │
          ▼
  stdout (sorted, pipe-separated rows)
          │
          ▼
  Platform: stdout vs expected_output
          │
          ▼
  Verdict
```

---

## Key Constraints

| Constraint | Reason |
|------------|--------|
| `wrapper.py` must be ASCII-only | Non-ASCII bytes cause Judge0 to reject the source when `base64_encoded=false` |
| `enable_network: true` must be explicit | Without it the sandbox cannot do DNS resolution to reach `mysql-eval-server` |
| `USER_SQL = ""` must not be changed | This exact string is the injection anchor |
| Only `pymysql` is available | No other third-party packages are in the Judge0 image |
| NULL prints as `"NULL"` not `"None"` | Python's default `str(None)` is `"None"` which would cause mismatches |
