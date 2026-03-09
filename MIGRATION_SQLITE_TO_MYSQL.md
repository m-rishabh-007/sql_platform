# Migration: SQLite → MySQL Execution Engine

**Date:** 7 March 2026  
**Scope:** Switch SQL problem execution from SQLite (in-process) to MySQL (networked container)

---

## Why this was done

The original execution model used `sqlite3` (Python standard library) inside Judge0's
Python sandbox. This covered ~95% of standard SQL but blocked MySQL-specific syntax:
`DATEDIFF`, `IFNULL`, `STR_TO_DATE`, certain window functions, etc.

The goal was to run contestant SQL against a **real MySQL instance** while keeping the
existing Judge0 + Python injection pipeline intact.

---

## Architecture after this change

```
Contestant submits SQL
        │
        ▼
Judge0 worker (language_id: 71 — Python)
  └─ wrapper.py is executed
      ├─ reads JSON rows from stdin
      ├─ connects to mysql-eval-server (internal Docker network)
      ├─ CREATE DATABASE sandbox_<uuid>
      ├─ seeds table from JSON rows
      ├─ executes USER_SQL (contestant's query)
      ├─ prints sorted pipe-separated output to stdout
      └─ DROP DATABASE sandbox_<uuid>   ← always, even on error
```

The `generator.py`, `orchestrator_sql.py`, `examples.json`, and `config.json` files
are **completely unchanged** — the problem-definition layer is decoupled from the
execution layer.

---

## Files changed

### 1. `judge0-submission-system/Dockerfile.worker` — NEW FILE

**Path:** `/home/rishabh/Documents/platform/judge0-submission-system/Dockerfile.worker`

**What it does:**  
Extends the official `judge0/judge0:1.13.1` image and installs `pymysql` into the
system Python. This is necessary because Judge0's default image only ships with the
Python standard library — `pymysql` is a third-party package and would cause an
immediate `ModuleNotFoundError` without this.

```dockerfile
FROM judge0/judge0:1.13.1
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip \
    && pip3 install pymysql \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

**Rebuild command:**
```bash
docker compose build worker
```

---

### 2. `judge0-submission-system/mysql/init.sql` — NEW FILE

**Path:** `/home/rishabh/Documents/platform/judge0-submission-system/mysql/init.sql`

**What it does:**  
Automatically executed by MySQL on first container start (mounted into
`/docker-entrypoint-initdb.d/`). Creates the restricted `judge0_runner` account.

**Security model:**
- `judge0_runner` has `GRANT ALL` **only** on databases matching `sandbox_%`
- Zero access to any other database, including `mysql` itself
- Cannot escalate or re-delegate permissions (no `GRANT OPTION`)
- Ephemeral `sandbox_<uuid>` databases are created and dropped per submission

> ⚠️ Change the password `J0runner!secure99` before any shared/production deployment.

---

### 3. `judge0-submission-system/docker-compose.yml` — MODIFIED

**Path:** `/home/rishabh/Documents/platform/judge0-submission-system/docker-compose.yml`

**Three changes:**

#### a) `worker` service — switched from image pull to custom build
```yaml
# Before
worker:
  image: judge0/judge0:1.13.1

# After
worker:
  build:
    context: .
    dockerfile: Dockerfile.worker
```
Also added to `worker`:
- `MYSQL_EVAL_HOST=mysql-eval-server` and `MYSQL_RUNNER_PASSWORD` environment variables
- `mysql-eval-server: condition: service_healthy` in `depends_on` — worker won't
  start until MySQL is ready

#### b) `mysql-eval-server` service — NEW SERVICE added
```yaml
mysql-eval-server:
  image: mysql:8.0
  volumes:
    - mysql_data:/var/lib/mysql
    - ./mysql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
  # Port 3306 intentionally NOT published to host
  healthcheck: ...
```
- MySQL 8.0 on the internal Docker network only — not reachable from outside
- `init.sql` bootstraps `judge0_runner` on first start
- Healthcheck ensures worker waits for MySQL to be fully ready

#### c) `mysql_data` volume — added to `volumes:` block
```yaml
volumes:
  data:
  log:
  mysql_data:   # ← new
```

---

### 4. `judge0-submission-system/judge0.conf` — MODIFIED

**Path:** `/home/rishabh/Documents/platform/judge0-submission-system/judge0.conf`

**What changed:**
```ini
# Before
ENABLE_NETWORK=

# After
ENABLE_NETWORK=true
```

**Why:** By default, Judge0's `isolate` sandbox drops all network namespaces. Without
this, `pymysql.connect(host='mysql-eval-server', ...)` would time out — the Python
process inside the sandbox cannot reach any TCP socket.

**Security note:** `ENABLE_NETWORK=true` allows sandboxed code to make outbound TCP
connections. The `judge0_runner` RBAC on MySQL is the containment boundary — malicious
SQL like `DROP DATABASE mysql` will be rejected by MySQL's permission system.

---

### 5. `manager_direct_reports/wrapper.py` -- REWRITTEN

**Path:** `/home/rishabh/sql_platform/manager_direct_reports/wrapper.py`

**What changed:**

| Before | After |
|--------|-------|
| `import sqlite3` | `import pymysql`, `import uuid` |
| `sqlite3.connect(":memory:")` | `pymysql.connect(host='mysql-eval-server', ...)` |
| Single in-process DB | `CREATE DATABASE sandbox_<uuid>` per submission |
| `:name` SQLite placeholders | `%s` positional placeholders (PyMySQL syntax) |
| No teardown needed | `DROP DATABASE sandbox_<uuid>` in `finally` block |
| `TEXT` / `INTEGER` column types | `VARCHAR(255)` / `INT` (real MySQL types) |
| Unicode chars in comments OK | **ASCII-only required** (see note below) |

**The injection anchor is unchanged:**
```python
USER_SQL = ""   # <- exact string, platform replaces this at contest time
```

**ASCII-only requirement:**
Judge0 rejects source code containing non-ASCII bytes when `base64_encoded=false`.
The symptom is HTTP 201 with `{"error":"some attributes cannot be converted to UTF-8"}`
and the submission falls back to async worker execution where the isolate sandbox has
no Docker DNS -- so `mysql-eval-server` cannot be resolved. All comments and string
literals in `wrapper.py` and `solution.py` must use only ASCII characters.
Use `--` instead of em dashes, `!!` or `WARNING:` instead of emoji.

**Key design decisions:**
- `uuid.uuid4().hex` as schema name -> zero collision between concurrent submissions
- `finally` block guarantees `DROP DATABASE` even if the contestant's SQL raises an exception
- `pymysql` returns Python `None` for SQL `NULL` -- same as `sqlite3` -- so `_format_output`
  null-handling logic is identical

---

### 6. `manager_direct_reports/solution.py` — REWRITTEN

**Path:** `/home/rishabh/sql_platform/manager_direct_reports/solution.py`

**What changed:** Exact same rewrite as `wrapper.py`. The only difference between
`wrapper.py` and `solution.py` is that `solution.py` has `USER_SQL` pre-filled with
the reference SQL from `solution.sql`.

Used by `orchestrator_sql.py` to generate `expected_output` for every test case.

---

## Files NOT changed

| File | Reason |
|------|--------|
| `generator.py` | Unchanged -- still emits JSON rows; execution layer doesn't affect it |
| `solution.sql` | Unchanged -- pure SQL reference, no execution dependency |
| `template.sql` | Unchanged -- contestant starter stub |
| `examples.json` | Unchanged -- expected outputs stay valid (same query, same data) |
| `config.json` | Unchanged |
| `schema.sql` | Unchanged -- DDL reference only |
| `sql_engine/sql_executor.py` | Unchanged -- local dev helper, not used in Judge0 |

## Files changed (summary)

| File | Change |
|------|--------|
| `orchestrator_sql.py` | Added `"enable_network": True` to every Judge0 submission |
| `wrapper.py` | Rewritten: sqlite3 -> pymysql + sandbox_<uuid> pattern; ASCII-only |
| `solution.py` | Same rewrite as wrapper.py; ASCII-only |
| `judge0/docker-compose.yml` | Added mysql-eval-server service + `--default-authentication-plugin=mysql_native_password` |
| `judge0/mysql/init.sql` | Created; bootstraps judge0_runner with mysql_native_password |
| `judge0/judge0.conf` | `ENABLE_NETWORK=true` |

---

## Deployment steps (run once)

The deployment now lives at `sql_platform/judge0/` (not in the original
`judge0-submission-system` directory — that was reverted to clean state).

```bash
cd /home/rishabh/sql_platform/judge0

# 1. Build the custom worker image (Dockerfile.worker)
docker compose build worker

# 2. Bring up all 5 services (db, redis, mysql-eval-server, server, worker)
docker compose up -d

# 3a. First-time only: run DB schema migrations
docker compose run --rm server rails db:migrate

# 3b. First-time only: seed the languages table
docker compose run --rm server rails db:seed

# 3c. If server keeps restarting (stale PID bug):
docker compose stop server && docker compose rm -f server && docker compose up -d server

# 4. Verify Judge0 accepts Python submissions
curl -s -X POST "http://localhost:3000/submissions?base64_encoded=false&wait=true&fields=stdout,status" \
  -H "Content-Type: application/json" \
  -d '{"source_code":"print(\"ok\")","language_id":71,"stdin":""}' | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['status']['description'], d.get('stdout','').strip())"
# Expected: Accepted ok
```

---

## Resolved: pymysql sandbox + MySQL auth + network

**Status (2025-03-07): Fully resolved. End-to-end test suite generation passing.**

### What was fixed

All three blockers that prevented SQL wrapper submissions from running were resolved in sequence:

**1. pymysql not visible inside isolate sandbox**
Root cause: isolate reconstructs the sandbox from base image layers only, skipping any
Dockerfile-added layers. Fix: collapsed all 50+ layers into a single flat layer via
`docker export | docker import`, tagged as `judge0/judge0:1.13.1-mysql`. Isolate now sees
one layer (squashed) which contains pymysql at the standard site-packages path.

**2. MySQL caching_sha2_password auth rejected by pymysql sandbox**
MySQL 8.0 defaults to `caching_sha2_password`, which pymysql can only handle with the
`cryptography` package (not available in the sandbox). Fix:
- Added `--default-authentication-plugin=mysql_native_password` to `mysql-eval-server`
  command in `docker-compose.yml`
- Changed `mysql/init.sql` to `IDENTIFIED WITH mysql_native_password BY '...'`
- Wiped `judge0_mysql_data` volume and recreated the container so `init.sql` re-ran

Acceptance test confirming the fix:
```bash
curl -s -X POST "http://localhost:3000/submissions?base64_encoded=false&wait=true&fields=stdout,stderr,status" \
  -H "Content-Type: application/json" \
  -d '{"source_code":"import pymysql\nconn=pymysql.connect(host=\"mysql-eval-server\",user=\"judge0_runner\",password=\"J0runner!secure99\",autocommit=True)\nwith conn.cursor() as c:\n    c.execute(\"SELECT VERSION()\")\n    print(\"MySQL:\",c.fetchone()[0])\nconn.close()","language_id":71,"stdin":"","enable_network":true}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status']['description']); print(d.get('stdout','').strip())"
# Output: Accepted
#         MySQL: 8.0.45
```

**3. DNS resolution failure inside isolate sandbox + wrapper non-ASCII bytes**
`ENABLE_NETWORK=true` in `judge0.conf` sets the default but Judge0 still requires the
per-submission field `"enable_network": true` to actually open the network namespace.
Additionally, `wrapper.py` contained UTF-8 characters (em dash, warning emoji, arrow)
which caused Judge0 to reject synchronous execution. Both fixes applied:
- Added `"enable_network": True` to the `submit_to_judge0` payload in `orchestrator_sql.py`
- Replaced all non-ASCII characters in `wrapper.py` and `solution.py` with ASCII equivalents
  (`--` for em dash, `!!` for warning emoji, `->` for arrow)

---

## Before going to production -- checklist

- [x] Resolve pymysql-in-sandbox blocker (Option A -- squash image)
- [ ] Change `J0runner!secure99` in `mysql/init.sql` AND in `wrapper.py` / `solution.py`
- [ ] Set a strong `MYSQL_ROOT_PASSWORD` in `docker-compose.yml`
- [ ] Confirm Docker network blocks `mysql-eval-server` from public internet
- [ ] Rebuild worker image after every change to `Dockerfile.worker`
- [x] Regenerate `manager_direct_reports_sql_testcases.json` via `orchestrator_sql.py`
