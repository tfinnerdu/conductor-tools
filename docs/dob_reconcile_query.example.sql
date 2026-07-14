-- Example query for DOB_RECONCILE_SQL_FILE (DOB Repair "Fetch via SQL" source).
--
-- This is a STARTING TEMPLATE, not a working query — replace the table/view
-- names and column expressions with whatever your Colleague reporting
-- database (ODS) actually exposes. Copy this file, edit your copy, and point
-- DOB_RECONCILE_SQL_FILE at it.
--
-- Requirements enforced by app/dob_sql_source.py before this ever runs:
--   - exactly one statement (no trailing/leading extra statements)
--   - must start with SELECT or WITH
--   - must not contain INSERT/UPDATE/DELETE/DROP/ALTER/EXEC/MERGE/TRUNCATE/
--     CREATE/GRANT/REVOKE/sp_*/INTO anywhere in the statement (INTO is
--     blocked because T-SQL's SELECT ... INTO creates a table)
--   (that text-level check is a footgun-catcher, not the real security
--   boundary — grant the DOB_RECONCILE_DB_USER login SELECT-only permission
--   on these views at the database level; see warning.md)
--
-- Output columns MUST be aliased exactly as below — these are the names
-- app/dob_detector.py's DEFAULT_COLUMNS maps onto the same Record shape the
-- CSV upload path produces:

SELECT
    p.person_id                AS person_id,
    p.last_name                AS last_name,
    p.first_name                AS first_name,
    p.middle_name               AS middle_name,
    p.birth_date                AS birth_date,
    p.address_line_1           AS addr_line1,
    p.city                     AS city,
    p.state                    AS state,
    p.zip_code                 AS zip,
    p.preferred_email          AS email,
    p.preferred_phone          AS phone,
    p.record_origin            AS origin,
    p.created_date             AS created_date
FROM dbo.person_reporting_view AS p
WHERE p.birth_date IS NOT NULL;
