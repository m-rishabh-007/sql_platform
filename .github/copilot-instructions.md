# AI Agent Guide: sql_platform

## What this project is

A SQL problem execution engine for a LeetCode-style competitive programming platform.
Users write MySQL-style SQL. The platform wraps it in Python, runs it against an
in-memory SQLite database via Judge0 (language ID 71 = Python), and grades the output.

**Read first:** [PLATFORM_CONTEXT.md](../PLATFORM_CONTEXT.md) — authoritative reference
for all file conventions, patterns, and common pitfalls.

---

## Critical context (read before every task)

- **Judge0 runs at `http://localhost:3000`** (Python language_id: 71)
- **Injection placeholder** in every `wrapper.py` is the exact string `USER_SQL = ""`
- **stdout is always sorted** lexicographically (case-insensitive) — ORDER BY in SQL is irrelevant for grading
- **stdin = JSON array** (single table) or **JSON dict** (multi-table) of row objects
- **No trailing newline** in `expected_output` fields

---

## Repo structure

```
sql_platform/
├── orchestrator_sql.py          — test suite generator (uses Judge0)
├── sql_engine/sql_executor.py   — local dev helper (never in Judge0)
├── PLATFORM_CONTEXT.md          — full pattern reference
├── README.md
├── .gitignore
├── manager_direct_reports/      — first problem (9 files, all complete)
└── <future_problems>/           — one folder per problem
```

---

## Problem folder (9 files per problem)

| File | Purpose |
|------|---------|
| `description.txt` | Competition problem statement |
| `schema.sql` | CREATE TABLE DDL (reference) |
| `solution.sql` | Correct SQL answer |
| `template.sql` | Contestant starter (blank SELECT) |
| `wrapper.py` | Platform injection template — contains `USER_SQL = ""` |
| `solution.py` | Self-contained Python: wrapper + solution SQL embedded |
| `generator.py` | CLI: outputs JSON rows for edge/small/medium/large/stress |
| `examples.json` | 2–3 visible examples |
| `config.json` | Generation bucket counts |

---

## Creating a new SQL problem

### Step 1 — Copy the canonical template
```bash
cp -r manager_direct_reports/ my_new_problem/
cd my_new_problem/
```

### Step 2 — Edit all 9 files

**description.txt** — write the problem statement in competition format.

**schema.sql** — the CREATE TABLE DDL for the new problem's tables.

**solution.sql** — the correct SELECT query. Pure SQL, no Python.

**template.sql** — minimal stub:
```sql
-- Available table: TableName (col1, col2, ...)
SELECT

```

**wrapper.py** — update `_SCHEMA_DDL` and `_INSERT_SQL` to match the new table.
Keep everything else identical. The `USER_SQL = ""` line must not change.

**solution.py** — same as `wrapper.py` but with `USER_SQL = """..."""` filled in
from `solution.sql`. Update schema/insert to match as well.

**generator.py** — generate realistic rows for the new schema. Output a JSON array
(or dict for multi-table).

**examples.json** — 2–3 varied visible examples. `expected_output` must match
`solution.py` output exactly (run `echo '<stdin>' | python3 solution.py` to verify).

**config.json** — adjust counts if needed; defaults (3/5/5/3/2) work for most problems.

### Step 3 — Smoke test
```bash
python3 -m py_compile solution.py wrapper.py generator.py
python3 generator.py small --rng-seed 42 | python3 solution.py
```

### Step 4 — Generate test suite
```bash
python3 ../orchestrator_sql.py -p .
```

---

## orchestrator_sql.py workflow

1. Reads `wrapper.py` + `solution.sql`
2. Injects SQL into wrapper: `USER_SQL = ""` → `USER_SQL = """<sql>"""`
3. Runs `generator.py` for each rule in `config.json`
4. POSTs the combined Python + JSON stdin to Judge0 at `localhost:3000`
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
# stdin = JSON test case
```

---

## Debugging Judge0

```bash
# Health check
curl -s http://localhost:3000/system_info | head -c 80

# Manual submission test
curl -X POST http://localhost:3000/submissions?base64_encoded=false&wait=true \
  -H 'Content-Type: application/json' \
  -d '{"source_code":"import json,sys\nprint(len(json.loads(sys.stdin.read())))","language_id":71,"stdin":"[1,2,3]"}'

# Server stuck on stale PID (restart loop fix):
docker compose stop server && docker compose rm -f server && docker compose up -d server
sleep 15 && curl -s http://localhost:3000/system_info | head -c 80
```

Judge0 status codes:
- `3` = Accepted ✅
- `6` = Compilation Error
- `11` = Runtime Error (NZEC)
- `13` = Internal Error

---

## Common mistakes to avoid

1. **Changing `USER_SQL = ""`** — this exact string is the injection anchor. Any extra spaces or different quotes break injection.

2. **Forgetting to update both `wrapper.py` AND `solution.py`** — they must stay in sync on schema/insert/output logic.

3. **Wrong NULL handling** — Python `None` must print as `"NULL"` (uppercase), not `"None"` or `"null"`.

4. **Not sorting output** — never rely on SQL ORDER BY for grading. Always sort in `_format_output`.

5. **Multi-line stdin in examples.json** — `stdin` must be a single-line JSON string (the JSON array/dict on one line).

6. **Wrong expected_output** — always regenerate via `echo '<stdin>' | python3 solution.py` rather than writing it by hand.

7. **Generator not handling all 5 rule types** — every `generate_case` function must handle `edge_cases`, `small`, `medium`, `large`, and `stress` or you'll get a `ValueError` during test suite generation.

---

## Multi-table problems

For problems with JOIN across two tables (e.g., Employee + Department):
- `stdin` becomes a JSON dict: `{"Employee": [...], "Department": [...]}`
- `wrapper.py`/`solution.py`: update `_create_db` to accept a dict and insert into multiple tables
- `generator.py`: `return json.dumps({"Table1": rows1, "Table2": rows2})`
- `examples.json`: `"stdin"` is the serialized dict string

Full pattern in [PLATFORM_CONTEXT.md](../PLATFORM_CONTEXT.md#multi-table-problem-pattern).

---

## What NOT to do

- Do NOT add external Python packages to `wrapper.py` or `solution.py` — Judge0's Python environment only has the standard library.
- Do NOT put logic in `template.sql` — it should be a blank stub only.
- Do NOT use `raise NotImplementedError` anywhere — return empty results instead.
- Do NOT hardcode test data in `solution.py` — it reads from `sys.stdin`.
- Do NOT run `orchestrator_sql.py` before verifying Judge0 is healthy.
