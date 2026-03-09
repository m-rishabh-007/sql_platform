# sql_platform

SQL problem execution engine for a LeetCode-style competitive programming platform.

Users write MySQL-style SQL queries in the browser. The platform wraps their SQL in
Python, submits it to Judge0 (Python language_id 71), which connects to a dedicated
`mysql-eval-server` container, runs the query against an ephemeral `sandbox_<uuid>`
database seeded from JSON test data, and grades the sorted output.

Full MySQL 8.0 dialect support -- no SQLite shims, no missing functions.

---

## Repository structure

```
sql_platform/
├── orchestrator_sql.py          <- generates test suites for any problem
├── PLATFORM_CONTEXT.md          <- full pattern reference (read before coding)
├── MIGRATION_SQLITE_TO_MYSQL.md <- migration history and architecture notes
├── sql_engine/
│   ├── sql_executor.py          <- local dev / smoke-test helper (not used in Judge0)
│   └── __init__.py
├── judge0/                      <- self-hosted Judge0 stack (5 containers)
│   ├── docker-compose.yml
│   ├── judge0.conf
│   ├── mysql/init.sql            <- bootstraps judge0_runner MySQL account
│   └── ...
├── manager_direct_reports/      <- first problem (9 files)
│   ├── description.txt
│   ├── schema.sql
│   ├── solution.sql             <- reference SQL
│   ├── template.sql             <- contestant starter
│   ├── wrapper.py               <- platform injection template
│   ├── solution.py              <- self-contained (for orchestrator)
│   ├── generator.py             <- generates random JSON test data
│   ├── examples.json            <- visible examples (JSON stdin)
│   └── config.json              <- test generation buckets
└── .github/
    └── copilot-instructions.md  <- AI agent guide
```

---

## Execution flow

```
Contestant writes SQL in editor (template.sql is the starter)
         |
         v
Platform injects SQL into wrapper.py:
   USER_SQL = ""   ->   USER_SQL = """SELECT name FROM Employee..."""
         |
         v
Combined Python file submitted to Judge0 (language_id: 71, enable_network: true)
stdin = JSON array of table rows (from generator.py)
         |
         v
wrapper.py connects to mysql-eval-server (internal Docker network)
  CREATE DATABASE sandbox_<uuid> -> seed rows -> run USER_SQL
  -> sorted stdout -> DROP DATABASE sandbox_<uuid>
         |
         v
Grader compares stdout to expected_output from testcases.json
```

---

## Judge0 setup

The platform stack lives in `judge0/` and runs **5 containers**:
`server`, `worker`, `db` (PostgreSQL), `redis`, `mysql-eval-server`.

```bash
cd judge0/
docker compose up -d

# Health check:
curl -s http://localhost:3000/system_info | head -c 80

# Verify Python + MySQL works end-to-end:
curl -s -X POST "http://localhost:3000/submissions?base64_encoded=false&wait=true&fields=stdout,status" \
  -H "Content-Type: application/json" \
  -d '{"source_code":"import pymysql\nconn=pymysql.connect(host=\"mysql-eval-server\",user=\"judge0_runner\",password=\"J0runner!secure99\",autocommit=True)\nprint(\"ok\")\nconn.close()","language_id":71,"stdin":"","enable_network":true}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status']['description'])"
# Expected: Accepted
```

---

## stdin / stdout contract

### stdin
JSON array of row objects matching the problem's table schema:
```json
[
  {"id": 101, "name": "John", "department": "A", "managerId": null},
  {"id": 102, "name": "Dan",  "department": "A", "managerId": 101}
]
```

### stdout
- One result row per line
- Multiple columns separated by `|`
- `NULL` for SQL NULL values
- Rows **sorted lexicographically** (case-insensitive) — so "any order" problems grade deterministically

---

## Generating test suites

```bash
# From the project root:
python3 orchestrator_sql.py -p manager_direct_reports/

# Output: manager_direct_reports/manager_direct_reports_sql_testcases.json
# Contains visible + hidden test cases with expected_output from Judge0
```

---

## Smoke-testing a problem locally

```bash
cd manager_direct_reports/

# Test solution.py directly (uses MySQL via subprocess -- requires Judge0 stack up)
echo '[{"id":101,"name":"John","department":"A","managerId":null},
       {"id":102,"name":"Dan","department":"A","managerId":101},
       {"id":103,"name":"James","department":"A","managerId":101},
       {"id":104,"name":"Amy","department":"A","managerId":101},
       {"id":105,"name":"Anne","department":"A","managerId":101},
       {"id":106,"name":"Ron","department":"B","managerId":101}]' \
  | python3 solution.py
# Expected: John

# Run generator
python3 generator.py small --rng-seed 42

# Full rule types: edge_cases | small | medium | large | stress
```

---

## Adding a new SQL problem

1. Copy an existing problem as a starter:
   ```bash
   cp -r manager_direct_reports/ my_new_problem/
   cd my_new_problem/
   ```

2. Edit all 9 files — see [PLATFORM_CONTEXT.md](PLATFORM_CONTEXT.md) for full conventions.

3. Run smoke test:
   ```bash
   python3 generator.py small --rng-seed 42 | python3 solution.py
   ```

4. Generate test suite:
   ```bash
   python3 ../orchestrator_sql.py -p .
   ```

---

## SQL dialect

Problems run against **MySQL 8.0** -- full dialect support:

| Feature | Supported |
|---------|----------|
| SELECT, WHERE, GROUP BY, HAVING | Yes |
| JOIN (INNER, LEFT, RIGHT) | Yes |
| Subqueries, IN, EXISTS | Yes |
| CTEs (WITH ... AS) | Yes |
| Window functions (ROW_NUMBER, RANK, etc.) | Yes |
| LIMIT / OFFSET | Yes |
| IFNULL / COALESCE / CASE | Yes |
| DATEDIFF, STR_TO_DATE, DATE_FORMAT | Yes (MySQL native) |
| ILIKE | No -- use `LOWER(col) LIKE ...` |

---

## Files per problem (9 total)

| File | Role |
|------|------|
| `description.txt` | Competition-style problem statement |
| `schema.sql` | CREATE TABLE DDL (reference only) |
| `solution.sql` | Reference SQL — correct answer |
| `template.sql` | Contestant starter (blank SELECT stub) |
| `wrapper.py` | Platform injection template — `USER_SQL = ""` |
| `solution.py` | Standalone Python = wrapper + solution SQL (used by orchestrator) |
| `generator.py` | Emits random JSON rows for edge/small/medium/large/stress cases |
| `examples.json` | 2–3 visible examples with JSON stdin |
| `config.json` | Test generation bucket counts |
