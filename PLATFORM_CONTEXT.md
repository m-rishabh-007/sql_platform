# SQL Platform — Complete Pattern Reference

## Problem file conventions

### wrapper.py — the injection contract

Every `wrapper.py` must have exactly this line in the right place:

```python
USER_SQL = ""
```

At contest time the platform does a literal string replacement:
```python
wrapper_code.replace('USER_SQL = ""', f'USER_SQL = """\n{contestant_sql}\n"""')
```

The replaced file is then submitted to Judge0 as Python (language_id: 71).

**Critical rules for wrapper.py:**
- Must import `sys`, `json`, `sqlite3` and nothing else (no external packages in Judge0)
- `_SCHEMA_DDL` = the `CREATE TABLE` statement(s) for this problem
- `_INSERT_SQL`  = the parameterized `INSERT INTO ... VALUES (:col, ...)` statement
- `_create_db(rows)` = builds the in-memory SQLite DB from the JSON rows
- `_run_query(conn, sql)` = executes USER_SQL and returns (rows, columns)
- `_format_output(rows)` = sorts + prints rows, pipe-separated

### solution.py — orchestrator target

Identical logic to `wrapper.py` but with `USER_SQL` already filled in with the
reference SQL (same as `solution.sql`).

This is the file the orchestrator submits to Judge0 to get `expected_output`.

**Keeping wrapper.py and solution.py in sync:**
Any change to the schema DDL, insert SQL, or output formatting must be applied to
BOTH files. The only difference between them is that `solution.py` has a non-empty
`USER_SQL`.

### solution.sql — reference SQL

Pure SQL — no Python, no comments that conflict with SQLite. Stored separately so:
- It can be displayed in an admin UI as the canonical answer
- `orchestrator_sql.py` injects it into `wrapper.py` during test suite generation
- It can be submitted directly to a real MySQL instance for verification

### template.sql — contestant starter

Keep it minimal — just enough to show the table name and a blank SELECT:
```sql
-- Write your MySQL query statement below
-- Available table: Employee (id, name, department, managerId)

SELECT

```

NO solution logic. NO hints beyond the table name.

### generator.py — test data generator

CLI contract (same as Python/C++ problems):
```bash
python3 generator.py <rule_type> --args '{}' --rng-seed 42
```
Output: a single JSON array printed to stdout (NOT a dict, NOT multi-line wrapper).

Five rule types with size guidelines:
| rule_type   | typical row count  | purpose                           |
|-------------|-------------------|-----------------------------------|
| edge_cases  | 1–6 rows          | boundary conditions               |
| small       | 6–15 rows         | manual-verifiable cases           |
| medium      | 20–80 rows        | typical usage                     |
| large       | 100–500 rows      | performance check                 |
| stress      | 1000–5000 rows    | max-constraint stress test        |

**Determinism:** always initialize `rng = random.Random(args.get("seed"))` so the
same seed always produces the same data.

### examples.json — visible test cases

```json
[
  {
    "stdin": "<JSON array as a single-line string>",
    "expected_output": "<exact stdout, no trailing newline>",
    "visibility": "visible"
  }
]
```

`expected_output` must match `solution.py` output exactly.
For empty result sets, `"expected_output": ""`.

### config.json — generation buckets

```json
{
  "generation_logic": [
    {"type": "edge_cases", "count": 3, "args": {}},
    {"type": "small",      "count": 5, "args": {}},
    {"type": "medium",     "count": 5, "args": {}},
    {"type": "large",      "count": 3, "args": {}},
    {"type": "stress",     "count": 2, "args": {}}
  ]
}
```

---

## stdin/stdout output format

### stdin (JSON array)
Single table — list of row dicts:
```json
[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
```

Multi-table — dict of table name → list of row dicts:
```json
{
  "Employee":   [{"id": 1, "name": "Alice", "managerId": null}],
  "Department": [{"id": 10, "name": "Eng"}]
}
```
When using multi-table format, `wrapper.py` must parse the dict and insert each
table separately. Update `_create_db` accordingly.

### stdout (graded output)
```
Alice
Bob|Engineering
NULL
```
Rules:
- One result row per line
- Columns separated by `|`
- `NULL` (uppercase) for SQL NULL values
- Rows sorted lexicographically (case-insensitive) by all columns left-to-right

---

## Multi-table problem pattern

When a problem has more than one table (e.g., Employee + Department):

```python
# wrapper.py — multi-table _create_db
_SCHEMA_DDL = """
CREATE TABLE Employee (id INTEGER, name TEXT, deptId INTEGER);
CREATE TABLE Department (id INTEGER, name TEXT);
"""

_INSERT_EMPLOYEE = "INSERT INTO Employee VALUES (:id, :name, :deptId)"
_INSERT_DEPARTMENT = "INSERT INTO Department VALUES (:id, :name)"

def _create_db(data):
    # data = {"Employee": [...], "Department": [...]}
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    for stmt in [s for s in _SCHEMA_DDL.split(";") if s.strip()]:
        cursor.execute(stmt)
    for row in data.get("Employee", []):
        cursor.execute(_INSERT_EMPLOYEE, row)
    for row in data.get("Department", []):
        cursor.execute(_INSERT_DEPARTMENT, row)
    conn.commit()
    return conn
```

```python
# generator.py — emit a dict instead of a list
import json
def generate_case(rule_type, args):
    ...
    return json.dumps({
        "Employee":   employee_rows,
        "Department": dept_rows,
    })
```

```json
// examples.json — stdin is a JSON dict serialized as string
{
  "stdin": "{\"Employee\": [...], \"Department\": [...]}",
  "expected_output": "..."
}
```

---

## Common pitfalls

### Wrong SQL output ordering
Always sort in `_format_output` — do NOT rely on SQL ORDER BY for grading.
The platform strips trailing whitespace and compares line by line.

### NULL handling
Python `None` → SQLite `NULL` → print as `"NULL"` (not `"None"`, not `"null"`).

```python
def _format_output(rows):
    rows_sorted = sorted(rows, key=lambda r: [
        str(v).lower() if v is not None else "" for v in r
    ])
    for row in rows_sorted:
        print("|".join("NULL" if v is None else str(v) for v in row))
```

### Integer vs string comparison in results
SQLite returns Python types: `INTEGER` columns come back as `int`, `TEXT` as `str`.
The `str(v)` in format_output handles this uniformly.

### Stale PID in Judge0 server
If the Judge0 server container is in a restart loop:
```bash
docker compose stop server && docker compose rm -f server && docker compose up -d server
sleep 15 && curl -s http://localhost:3000/system_info | head -c 80
```

### Injection placeholder missing
`orchestrator_sql.py` looks for exactly `USER_SQL = ""` (double-quote, no spaces around `=`).
If you rename or reformat it the injection will fail.

---

## Smoke test checklist (before running orchestrator)

```bash
cd <problem_dir>/

# 1. Syntax check
python3 -m py_compile solution.py wrapper.py generator.py

# 2. Generator works for all rule types
for rt in edge_cases small medium large stress; do
    echo -n "$rt: " && python3 generator.py $rt --rng-seed 1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'rows')"
done

# 3. Solution produces correct output for examples
python3 generator.py small --rng-seed 42 | python3 solution.py

# 4. Judge0 round-trip on example 1
python3 - <<'EOF'
import requests, json
with open("solution.py") as f: src = f.read()
with open("examples.json") as f: ex = json.load(f)[0]
r = requests.post("http://localhost:3000/submissions?base64_encoded=false&wait=true&fields=stdout,status",
    json={"source_code": src, "language_id": 71, "stdin": ex["stdin"]}).json()
out = (r.get("stdout") or "").strip()
exp = ex["expected_output"].strip()
print("✅ PASS" if out == exp else f"❌ FAIL\ngot:      '{out}'\nexpected: '{exp}'")
EOF
```
