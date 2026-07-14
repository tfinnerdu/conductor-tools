"""SQL Server data source for DOB Repair (PD0002124) — round 2.

An alternative to CSV upload: runs a single, server-administered SELECT
statement (the file at DOB_RECONCILE_SQL_FILE) against a read-only reporting
connection and maps the result rows into the same Record shape the CSV path
produces (see app/dob_detector.py), so the detector is agnostic to where the
rows came from.

The query text is drafted and owned by whoever configures this feature — this
module never builds or edits SQL. It only runs whatever is in that file
against DOB_RECONCILE_DB_*, and refuses to run anything but a single
read-only SELECT/WITH statement.

Design notes
------------
- pyodbc is an OPTIONAL dependency, imported once at module load behind a
  try/except. Environments that never configure this feature (or lack the
  system ODBC driver — pyodbc needs "ODBC Driver 17/18 for SQL Server" plus
  unixODBC on Linux hosts) can still import this module and run every other
  Conductor Companion tab; only fetch_records() requires it to be present.
- The read-only guard here is a footgun-catcher, NOT the real security
  boundary. The real boundary is granting DOB_RECONCILE_DB_USER a read-only
  (SELECT-only) role on whatever reporting views it touches. See warning.md.
- Values come back from pyodbc as native Python types (date, datetime,
  Decimal, etc.). Everything is stringified before handing rows to
  detector.record_from_row() — Python's date/datetime __str__() already
  produces the "%Y-%m-%d" / "%Y-%m-%d %H:%M:%S" shapes detector.parse_date()
  recognizes, so no special-casing is needed there.
"""
import os
import re

from app import dob_detector as detector

try:
    import pyodbc
except ImportError:  # optional dependency — only needed when this source runs
    pyodbc = None

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|EXECUTE|MERGE|TRUNCATE|CREATE|GRANT|REVOKE|sp_\w*|INTO)\b",
    re.IGNORECASE,
)


def is_configured() -> bool:
    return bool(
        os.environ.get("DOB_RECONCILE_SQL_FILE", "").strip()
        and os.environ.get("DOB_RECONCILE_DB_SERVER", "").strip()
        and os.environ.get("DOB_RECONCILE_DB_NAME", "").strip()
    )


def sql_file_path() -> str:
    return os.environ.get("DOB_RECONCILE_SQL_FILE", "").strip()


def validate_read_only(query: str) -> None:
    """Reject anything but a single read-only SELECT/WITH statement.

    Defense-in-depth only — see the module docstring. A determined author of
    DOB_RECONCILE_SQL_FILE could still work around a text-level check; the
    real safety boundary is the DB credential's own permissions.
    """
    statements = [s.strip() for s in query.split(";") if s.strip()]
    if not statements:
        raise ValueError(f"{sql_file_path()} contains no statement")
    if len(statements) > 1:
        raise ValueError(
            f"{sql_file_path()} must contain exactly one statement (found {len(statements)})"
        )

    stmt = statements[0]
    leading_match = re.match(r"\s*(\w+)", stmt)
    leading = leading_match.group(1).upper() if leading_match else ""
    if leading not in ("SELECT", "WITH"):
        raise ValueError(
            f"{sql_file_path()} must start with SELECT or WITH, found {leading or '(empty)'}"
        )
    if _WRITE_KEYWORDS.search(stmt):
        raise ValueError(
            f"{sql_file_path()} contains a disallowed keyword — read-only SELECT only"
        )


def read_query() -> str:
    path = sql_file_path()
    if not path:
        raise RuntimeError("DOB_RECONCILE_SQL_FILE is not configured")
    with open(path, "r", encoding="utf-8") as fh:
        query = fh.read().strip()
    validate_read_only(query)
    return query


def _connection_string() -> str:
    driver = os.environ.get("DOB_RECONCILE_DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.environ["DOB_RECONCILE_DB_SERVER"]
    database = os.environ["DOB_RECONCILE_DB_NAME"]
    user = os.environ.get("DOB_RECONCILE_DB_USER", "").strip()
    password = os.environ.get("DOB_RECONCILE_DB_PASSWORD", "")
    encrypt = os.environ.get("DOB_RECONCILE_DB_ENCRYPT", "yes")
    trust_cert = os.environ.get("DOB_RECONCILE_DB_TRUST_SERVER_CERT", "yes")

    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]
    if user:
        parts += [f"UID={user}", f"PWD={password}"]
    else:
        parts.append("Trusted_Connection=yes")
    parts += [f"Encrypt={encrypt}", f"TrustServerCertificate={trust_cert}"]
    return ";".join(parts)


def _row_to_dict(columns: list, row) -> dict:
    out = {}
    for col, val in zip(columns, row):
        out[col] = "" if val is None else str(val)
    return out


def fetch_records(columns: dict = None) -> list:
    """Run the configured query and return app.dob_detector.Record objects."""
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is not installed, or the system ODBC driver manager is "
            "missing. This feature needs pyodbc plus 'ODBC Driver 17/18 for "
            "SQL Server' (and unixODBC on Linux hosts) — see docs/user-guide.md."
        )

    query = read_query()
    conn = pyodbc.connect(_connection_string(), timeout=15, autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        col_names = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()

    cols = dict(detector.DEFAULT_COLUMNS)
    if columns:
        cols.update(columns)
    return [detector.record_from_row(_row_to_dict(col_names, row), cols) for row in rows]
