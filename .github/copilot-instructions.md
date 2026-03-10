# AI Agent Guide: sql_platform

## What this project is

A SQL problem execution engine for a LeetCode-style competitive programming platform.
Users write MySQL-style SQL. The platform wraps it in Python, submits it to Judge0
(language_id 71 = Python) with `enable_network: true`, which connects to a dedicated
`mysql-eval-server` container, runs the query against an ephemeral `sandbox_<uuid>`
MySQL database seeded from JSON test data, and grades the sorted output.

**Read first:** [PLATFORM_CONTEXT.md](../PLATFORM_CONTEXT.md) -- authoritative reference
for all file conventions, patterns, and common pitfalls.

---

## Critical context (read before every task)

- **Judge0 stack lives at** `/home/rishabh/sql_platform/judge0` (5 containers: server, worker, db, redis, mysql-eval-server)
- **Judge0 runs at `http://localhost:3000`** (Python language_id: 71)
- **Injection placeholder** in every `wrapper.py` is the exact string `USER_SQL = ""`
- **Every Judge0 submission must include `"enable_network": true`** -- without it the isolate sandbox cannot reach `mysql-eval-server` (DNS fails silently)
- **wrapper.py and solution.py must be ASCII-only** -- any non-ASCII byte (em dash, emoji, arrow) causes Judge0 to reject the source when `base64_encoded=false`, falling back to async execution where Docker DNS is unavailable
- **stdout is always sorted** lexicographically (case-insensitive) -- ORDER BY in SQL is irrelevant for grading
- **stdin = JSON array** (single table) or **JSON dict** (multi-table) of row objects
- **No trailing newline** in `expected_output` fields
- **MySQL auth**: `mysql-eval-server` uses `mysql_native_password` -- do not change this or pymysql will need the `cryptography` package which is not in the sandbox

---

## Repo structure

```
sql_platform/
├── orchestrator_sql.py          -- test suite generator (uses Judge0)
├── sql_engine/sql_executor.py   -- local dev helper (never in Judge0)
├── PLATFORM_CONTEXT.md          -- full pattern reference
├── MIGRATION_SQLITE_TO_MYSQL.md -- migration history and architecture notes
├── README.md
├── .gitignore
├── judge0/                      -- self-hosted Judge0 stack
│   ├── docker-compose.yml       -- 5 services: server, worker, db, redis, mysql-eval-server
│   ├── judge0.conf              -- ENABLE_NETWORK=true set here
│   └── mysql/init.sql           -- bootstraps judge0_runner account (mysql_native_password)
├── manager_direct_reports/      -- first problem (9 files, all complete)
└── <future_problems>/           -- one folder per problem
```

---

## Problem folder (9 files per problem)

| File | Purpose |
|------|---------|
| `description.txt` | Competition problem statement |
| `schema.sql` | CREATE TABLE DDL (reference) |
| `solution.sql` | Correct SQL answer |
| `template.sql` | Contestant starter (blank SELECT) |
| `wrapper.py` | Platform injection template -- contains `USER_SQL = ""` |
| `solution.py` | Self-contained Python: wrapper + solution SQL embedded |
| `generator.py` | CLI: outputs JSON rows for edge/small/medium/large/stress |
| `examples.json` | 2-3 visible examples |
| `config.json` | Generation bucket counts |

---

## Creating a new SQL problem

### Step 1 -- Copy the canonical template
```bash
cp -r manager_direct_reports/ my_new_problem/
cd my_new_problem/
```

### Step 2 -- Edit all 9 files

**description.txt** -- write the problem statement in competition format.

**schema.sql** -- the CREATE TABLE DDL for the new problem's tables (MySQL types: INT, VARCHAR, etc.).

**solution.sql** -- the correct SELECT query. Pure SQL, no Python.

**template.sql** -- minimal stub:
```sql
-- Available table: TableName (col1, col2, ...)
SELECT

```

**wrapper.py** -- update `_SCHEMA_DDL` (MySQL types) and `_INSERT_SQL` (`%s` placeholders)
to match the new table. Keep everything else identical. The `USER_SQL = ""` line must
not change. Must be ASCII-only (no em dashes, no emoji).

**solution.py** -- same as `wrapper.py` but with `USER_SQL = """..."""` filled in
from `solution.sql`. Update schema/insert to match as well. Also ASCII-only.

**generator.py** -- generate realistic rows for the new schema. Output a JSON array
(or dict for multi-table).

**examples.json** -- 2-3 varied visible examples. `expected_output` must match
`solution.py` output exactly (run `echo '<stdin>' | python3 solution.py` to verify).

**config.json** -- adjust counts if needed; defaults (3/5/5/3/2) work for most problems.

### Step 3 -- Smoke test
```bash
python3 -m py_compile solution.py wrapper.py generator.py
python3 generator.py small --rng-seed 42 | python3 solution.py
```

### Step 4 -- Generate test suite
```bash
python3 ../orchestrator_sql.py -p .
```

---

## orchestrator_sql.py workflow

1. Reads `wrapper.py` + `solution.sql`
2. Injects SQL into wrapper: `USER_SQL = ""` -> `USER_SQL = """<sql>"""`
3. Runs `generator.py` for each rule in `config.json`
4. POSTs the combined Python + JSON stdin to Judge0 at `localhost:3000` with `enable_network: true`
5. Collects `stdout` as `expected_output`
6. Writes `<problem_name>_sql_testcases.json`

Usage:
```bash
python3 orchestrator_sql.py -p <problem_dir>/
```

---

## Platform injection at contest time

When a contestant submits their SQL, the platform does:
```python
injected_code = wrapper_code.replace(
    'USER_SQL = ""',
    f'USER_SQL = """\n{contestant_sql.strip()}\n"""'
)
# Submit injected_code to Judge0 as Python (language_id=71)
# MUST include enable_network=true so wrapper can reach mysql-eval-server
# stdin = JSON test case
```

---

## Debugging Judge0

```bash
# Health check
curl -s http://localhost:3000/system_info | head -c 80

# Full MySQL round-trip test (acceptance test)
curl -s -X POST "http://localhost:3000/submissions?base64_encoded=false&wait=true&fields=stdout,stderr,status" \
  -H "Content-Type: application/json" \
  -d '{"source_code":"import pymysql\nconn=pymysql.connect(host=\"mysql-eval-server\",user=\"judge0_runner\",password=\"J0runner!secure99\",autocommit=True)\nwith conn.cursor() as c:\n    c.execute(\"SELECT VERSION()\")\n    print(\"MySQL:\",c.fetchone()[0])\nconn.close()","language_id":71,"stdin":"","enable_network":true}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status']['description']); print(d.get('stdout','').strip())"
# Expected: Accepted
#           MySQL: 8.0.x

# Server stuck on stale PID (restart loop fix):
cd /home/rishabh/sql_platform/judge0
docker compose stop server && docker compose rm -f server && docker compose up -d server
sleep 15 && curl -s http://localhost:3000/system_info | head -c 80

# Recreate MySQL (e.g. after auth config change -- wipes data):
docker compose stop mysql-eval-server && docker compose rm -f mysql-eval-server
docker volume rm judge0_mysql_data
docker compose up -d mysql-eval-server
# Then recreate worker (depends_on mysql):
docker compose stop worker && docker compose rm -f worker && docker compose up -d worker
```

Judge0 status codes:
- `3` = Accepted
- `5` = Time Limit Exceeded
- `6` = Compilation Error
- `11` = Runtime Error (NZEC)
- `13` = Internal Error

---

## Common mistakes to avoid

1. **Changing `USER_SQL = ""`** -- this exact string is the injection anchor. Any extra spaces or different quotes break injection.

2. **Forgetting to update both `wrapper.py` AND `solution.py`** -- they must stay in sync on schema/insert/output logic.

3. **Non-ASCII bytes in wrapper.py or solution.py** -- em dashes, arrows, emoji, etc. cause Judge0 to reject the submission when `base64_encoded=false`. The symptom is HTTP 201 with `{"error":"some attributes cannot be converted to UTF-8"}` and MySQL DNS failure. Every character must be ASCII (< 0x80). Use `--` not --, `->` not ->, `!!` not !!.

4. **Missing `enable_network: true` in Judge0 submissions** -- `ENABLE_NETWORK=true` in `judge0.conf` sets the default for submissions that omit the field, but it does not override an explicit `false`. Always pass `"enable_network": true` explicitly in the submission JSON.

5. **Wrong NULL handling** -- Python `None` must print as `"NULL"` (uppercase), not `"None"` or `"null"`.

6. **Not sorting output** -- never rely on SQL ORDER BY for grading. Always sort in `_format_output`.

7. **Multi-line stdin in examples.json** -- `stdin` must be a single-line JSON string (the JSON array/dict on one line).

8. **Wrong expected_output** -- always regenerate via `echo '<stdin>' | python3 solution.py` rather than writing it by hand.

9. **Generator not handling all 5 rule types** -- every `generate_case` function must handle `edge_cases`, `small`, `medium`, `large`, and `stress` or you'll get a `ValueError` during test suite generation.

10. **Wrong MySQL auth** -- `mysql-eval-server` uses `--default-authentication-plugin=mysql_native_password`. If you recreate the MySQL container without wiping `judge0_mysql_data` first, the old auth config persists and pymysql will fail with a `caching_sha2_password` error.

---

## Multi-table problems

For problems with JOIN across two tables (e.g., Employee + Department):
- `stdin` becomes a JSON dict: `{"Employee": [...], "Department": [...]}`
- `wrapper.py`/`solution.py`: update schema DDL and insert logic to handle the dict; use `%s` placeholders for all inserts
- `generator.py`: `return json.dumps({"Table1": rows1, "Table2": rows2})`
- `examples.json`: `"stdin"` is the serialized dict string

Full pattern in [PLATFORM_CONTEXT.md](../PLATFORM_CONTEXT.md) (see "Multi-table problem pattern" section).

---

## What NOT to do

- Do NOT add external Python packages beyond `pymysql` to `wrapper.py` or `solution.py` -- the Judge0 image (`judge0/judge0:1.13.1-mysql`) only has the standard library + pymysql baked in.
- Do NOT use `sqlite3` -- all execution now goes through `mysql-eval-server` via pymysql.
- Do NOT put non-ASCII characters in `wrapper.py` or `solution.py` -- see mistake #3 above.
- Do NOT put logic in `template.sql` -- it should be a blank stub only.
- Do NOT use `raise NotImplementedError` anywhere -- return empty results instead.
- Do NOT hardcode test data in `solution.py` -- it reads from `sys.stdin`.
- Do NOT run `orchestrator_sql.py` before verifying Judge0 is healthy.
- Do NOT recreate the MySQL container without `docker volume rm judge0_mysql_data` -- stale volume retains the old auth plugin.
