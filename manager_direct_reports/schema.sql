-- Schema for: Manager with at Least Five Direct Reports
-- RDBMS target: MySQL 8.0 / SQLite 3.x compatible

CREATE TABLE Employee (
    id          INT,            -- unique employee id (primary key)
    name        VARCHAR(50),    -- employee name
    department  VARCHAR(50),    -- department the employee belongs to
    managerId   INT             -- id of manager; NULL if top-level employee
);
