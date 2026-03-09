-- mysql/init.sql
-- Bootstraps the restricted `judge0_runner` account used by SQL problem wrappers.
--
-- This file is automatically executed by MySQL on first container start
-- (mounted into /docker-entrypoint-initdb.d/).
--
-- Security model:
--   - judge0_runner can ONLY operate on databases whose names start with "sandbox_"
--   - These are ephemeral per-submission databases, created and dropped by the wrapper
--   - judge0_runner has NO access to any other database, including `mysql` itself
--   - No GRANT OPTION: judge0_runner cannot re-delegate its own permissions
--
-- ⚠️  Change the password below before deploying to any shared/production environment.

CREATE USER IF NOT EXISTS 'judge0_runner'@'%' IDENTIFIED WITH mysql_native_password BY 'J0runner!secure99';

-- Full control only on sandbox_* databases (ephemeral, blow-away-safe)
GRANT ALL PRIVILEGES ON `sandbox_%`.* TO 'judge0_runner'@'%';

FLUSH PRIVILEGES;
