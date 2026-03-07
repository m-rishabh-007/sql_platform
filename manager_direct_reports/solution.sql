-- Reference solution: Manager with at Least Five Direct Reports
-- Write your MySQL query statement below

SELECT e1.name
FROM Employee e1
WHERE e1.id IN (
    SELECT managerId
    FROM Employee
    GROUP BY managerId
    HAVING COUNT(*) >= 5
);

-- Alternative using JOIN:
--
-- SELECT e1.name
-- FROM Employee e1
-- INNER JOIN Employee e2 ON e1.id = e2.managerId
-- GROUP BY e1.id, e1.name
-- HAVING COUNT(e2.id) >= 5;
