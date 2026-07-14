"""Tests for the DOB Repair SQL fetch source — app/dob_sql_source.py

pyodbc itself is never really invoked here (no live SQL Server in tests) —
either dob_sql_source.pyodbc is monkeypatched to a MagicMock, or set to None
to exercise the "optional dependency missing" path.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from app import dob_sql_source


class TestIsConfigured:
    def test_false_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("DOB_RECONCILE_SQL_FILE", raising=False)
        monkeypatch.delenv("DOB_RECONCILE_DB_SERVER", raising=False)
        monkeypatch.delenv("DOB_RECONCILE_DB_NAME", raising=False)
        assert dob_sql_source.is_configured() is False

    def test_true_when_all_required_vars_set(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT 1")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "sqlserver.doane.edu")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "ODS")
        assert dob_sql_source.is_configured() is True

    def test_false_when_partially_set(self, monkeypatch):
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", "/tmp/q.sql")
        monkeypatch.delenv("DOB_RECONCILE_DB_SERVER", raising=False)
        monkeypatch.delenv("DOB_RECONCILE_DB_NAME", raising=False)
        assert dob_sql_source.is_configured() is False


class TestValidateReadOnly:
    def test_accepts_plain_select(self):
        dob_sql_source.validate_read_only("SELECT person_id FROM persons")

    def test_accepts_with_cte(self):
        dob_sql_source.validate_read_only("WITH x AS (SELECT 1 AS a) SELECT a FROM x")

    def test_accepts_trailing_semicolon(self):
        dob_sql_source.validate_read_only("SELECT 1;")

    def test_rejects_multiple_statements(self):
        with pytest.raises(ValueError):
            dob_sql_source.validate_read_only("SELECT 1; SELECT 2;")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            dob_sql_source.validate_read_only("   ")

    def test_rejects_non_select_leading_keyword(self):
        with pytest.raises(ValueError):
            dob_sql_source.validate_read_only(
                "UPDATE persons SET birth_date = '1980-01-01'"
            )

    def test_rejects_select_into_table_creation(self):
        # SELECT ... INTO starts with SELECT but creates a table in T-SQL.
        with pytest.raises(ValueError):
            dob_sql_source.validate_read_only(
                "SELECT person_id INTO new_table FROM persons"
            )

    @pytest.mark.parametrize("statement", [
        "SELECT * FROM persons; DELETE FROM persons",
        "SELECT * FROM persons WHERE 1 = (DELETE FROM persons)",
        "SELECT * FROM persons; DROP TABLE persons",
        "SELECT * FROM persons; TRUNCATE TABLE persons",
        "SELECT * FROM persons; EXEC sp_who",
        "SELECT * FROM persons; GRANT SELECT ON persons TO public",
    ])
    def test_rejects_write_keywords_anywhere(self, statement):
        with pytest.raises(ValueError):
            dob_sql_source.validate_read_only(statement)


class TestReadQuery:
    def test_reads_and_validates_file(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT person_id FROM persons\n")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        assert dob_sql_source.read_query() == "SELECT person_id FROM persons"

    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("DOB_RECONCILE_SQL_FILE", raising=False)
        with pytest.raises(RuntimeError):
            dob_sql_source.read_query()

    def test_raises_on_unsafe_query_in_file(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("DELETE FROM persons")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        with pytest.raises(ValueError):
            dob_sql_source.read_query()


class TestConnectionString:
    def test_uses_sql_auth_when_user_set(self, monkeypatch):
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "sqlserver.doane.edu")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "ODS")
        monkeypatch.setenv("DOB_RECONCILE_DB_USER", "svc")
        monkeypatch.setenv("DOB_RECONCILE_DB_PASSWORD", "secret")
        conn_str = dob_sql_source._connection_string()
        assert "UID=svc" in conn_str
        assert "PWD=secret" in conn_str
        assert "Trusted_Connection" not in conn_str

    def test_uses_trusted_connection_when_no_user(self, monkeypatch):
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "sqlserver.doane.edu")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "ODS")
        monkeypatch.delenv("DOB_RECONCILE_DB_USER", raising=False)
        conn_str = dob_sql_source._connection_string()
        assert "Trusted_Connection=yes" in conn_str


class TestFetchRecords:
    def test_raises_when_pyodbc_unavailable(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT 1")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "s")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "d")
        monkeypatch.setattr(dob_sql_source, "pyodbc", None)
        with pytest.raises(RuntimeError):
            dob_sql_source.fetch_records()

    def test_maps_rows_into_records_and_closes_connection(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text(
            "SELECT person_id, last_name, first_name, birth_date, origin FROM persons"
        )
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "s")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "d")
        monkeypatch.setenv("DOB_RECONCILE_DB_USER", "svc")
        monkeypatch.setenv("DOB_RECONCILE_DB_PASSWORD", "secret")

        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("person_id",), ("last_name",), ("first_name",), ("birth_date",), ("origin",),
        ]
        mock_cursor.fetchall.return_value = [
            ("1001", "Smith", "John", date(1980, 4, 2), "INSTANT_ENROLL"),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        monkeypatch.setattr(dob_sql_source, "pyodbc", mock_pyodbc)

        records = dob_sql_source.fetch_records()

        assert len(records) == 1
        r = records[0]
        assert r.person_id == "1001"
        assert r.last_name == "Smith"
        assert r.birth_date == date(1980, 4, 2)
        assert r.is_ie is True
        mock_conn.close.assert_called_once()

    def test_null_values_become_empty_string(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("SELECT person_id, last_name, middle_name FROM persons")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "s")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "d")

        mock_cursor = MagicMock()
        mock_cursor.description = [("person_id",), ("last_name",), ("middle_name",)]
        mock_cursor.fetchall.return_value = [("2001", "Jones", None)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        monkeypatch.setattr(dob_sql_source, "pyodbc", mock_pyodbc)

        records = dob_sql_source.fetch_records()
        assert records[0].middle_name == ""

    def test_unsafe_query_never_reaches_the_database(self, monkeypatch, tmp_path):
        sql_file = tmp_path / "q.sql"
        sql_file.write_text("DELETE FROM persons")
        monkeypatch.setenv("DOB_RECONCILE_SQL_FILE", str(sql_file))
        monkeypatch.setenv("DOB_RECONCILE_DB_SERVER", "s")
        monkeypatch.setenv("DOB_RECONCILE_DB_NAME", "d")

        mock_pyodbc = MagicMock()
        monkeypatch.setattr(dob_sql_source, "pyodbc", mock_pyodbc)

        with pytest.raises(ValueError):
            dob_sql_source.fetch_records()
        mock_pyodbc.connect.assert_not_called()
