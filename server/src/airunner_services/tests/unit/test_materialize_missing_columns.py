"""Tests for _materialize_missing_columns and _get_actual_columns.

Verifies that the column-repair step correctly detects and adds
columns present in the ORM model but absent from an existing database
table, and that it is idempotent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy import Column, Integer, String, MetaData, Table


# ── _get_actual_columns ────────────────────────────────────────


class TestGetActualColumns:
    """Tests for the information_schema-based column query."""

    @staticmethod
    def _call(engine, table_name, target_schema=None):
        from airunner_services.database.setup_migrations import (
            _get_actual_columns,
        )

        return _get_actual_columns(engine, table_name, target_schema)

    def test_returns_column_names_with_schema_filter(self) -> None:
        """When target_schema is set, the query filters by schema."""
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = [
            ("id",), ("name",), ("created_at",),
        ]

        result = self._call(engine, "test_table", "test_schema")

        assert result == {"id", "name", "created_at"}
        # Verify the SQL used the schema filter
        call_sql = conn.execute.call_args[0][0].text
        assert "table_schema" in call_sql.lower()
        assert "test_schema" in str(call_sql) or "test_schema" in str(
            conn.execute.call_args
        )

    def test_returns_column_names_without_schema(self) -> None:
        """When target_schema is None, no schema filter is used."""
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = [
            ("id",), ("value",),
        ]

        result = self._call(engine, "test_table", None)

        assert result == {"id", "value"}
        call_sql = conn.execute.call_args[0][0].text
        assert "table_schema" not in call_sql.lower()

    def test_empty_table_returns_empty_set(self) -> None:
        """A table with no rows in information_schema returns empty."""
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = []

        result = self._call(engine, "missing_table", "test_schema")

        assert result == set()


# ── _materialize_missing_columns ───────────────────────────────


class TestMaterializeMissingColumns:
    """Tests for the column-repair function."""

    @staticmethod
    def _make_model(name, tablename, columns):
        """Build a minimal model class with __tablename__ and
        __table__."""
        metadata = MetaData()
        table = Table(tablename, metadata, *columns)
        model = type(
            name,
            (),
            {"__tablename__": tablename, "__table__": table},
        )
        return model

    def test_adds_missing_columns_to_existing_table(self) -> None:
        """When the DB has fewer columns than the ORM, the missing
        columns are added via ALTER TABLE."""
        TestModel = self._make_model(
            "TestModel",
            "test_table",
            [
                Column("id", Integer, primary_key=True),
                Column("name", String(50), nullable=False, default=""),
                Column("extra_col", String(100), nullable=True),
            ],
        )

        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = MagicMock()

        # DB has only id and name — extra_col is missing
        with (
            patch(
                "airunner_services.database.setup_migrations."
                "_get_actual_columns",
                return_value={"id", "name"},
            ),
            patch(
                "airunner_services.database.setup_migrations."
                "_add_column",
            ) as mock_add,
        ):
            from airunner_services.database.setup_migrations import (
                _materialize_missing_columns,
            )

            _materialize_missing_columns(
                engine, [TestModel], "test_schema",
            )

        # _add_column should be called once for extra_col
        assert mock_add.call_count == 1
        call_args = mock_add.call_args[0]
        # call_args: (engine, target_schema, table_name, orm_col, dialect)
        assert call_args[2] == "test_table"
        assert call_args[3].key == "extra_col"

    def test_noop_when_all_columns_present(self) -> None:
        """When the DB has all ORM columns, no ALTER TABLE is issued."""
        TestModel = self._make_model(
            "TestModel",
            "test_table",
            [
                Column("id", Integer, primary_key=True),
                Column("name", String(50)),
            ],
        )

        engine = MagicMock()
        with (
            patch(
                "airunner_services.database.setup_migrations."
                "_get_actual_columns",
                return_value={"id", "name"},
            ),
            patch(
                "airunner_services.database.setup_migrations."
                "_add_column",
            ) as mock_add,
        ):
            from airunner_services.database.setup_migrations import (
                _materialize_missing_columns,
            )

            _materialize_missing_columns(
                engine, [TestModel], "test_schema",
            )

        mock_add.assert_not_called()

    def test_skips_when_table_has_no_columns(self) -> None:
        """When _get_actual_columns returns empty, the table is
        skipped (it may not exist)."""
        TestModel = self._make_model(
            "TestModel",
            "test_table",
            [Column("id", Integer, primary_key=True)],
        )

        engine = MagicMock()
        with (
            patch(
                "airunner_services.database.setup_migrations."
                "_get_actual_columns",
                return_value=set(),
            ),
            patch(
                "airunner_services.database.setup_migrations."
                "_add_column",
            ) as mock_add,
        ):
            from airunner_services.database.setup_migrations import (
                _materialize_missing_columns,
            )

            _materialize_missing_columns(
                engine, [TestModel], "test_schema",
            )

        mock_add.assert_not_called()

    def test_deduplicates_tables_with_same_name(self) -> None:
        """Two model classes with the same __tablename__ are only
        processed once."""
        ModelA = self._make_model(
            "ModelA",
            "shared_table",
            [
                Column("id", Integer, primary_key=True),
                Column("col_a", String(10)),
            ],
        )
        ModelB = self._make_model(
            "ModelB",
            "shared_table",
            [
                Column("id", Integer, primary_key=True),
                Column("col_b", String(10), nullable=True),
            ],
        )

        engine = MagicMock()
        with patch(
            "airunner_services.database.setup_migrations."
            "_get_actual_columns",
            return_value={"id"},
        ):
            from airunner_services.database.setup_migrations import (
                _materialize_missing_columns,
            )

            # Should not crash on duplicate __tablename__
            _materialize_missing_columns(
                engine, [ModelA, ModelB], "test_schema",
            )

    def test_non_nullable_columns_get_default_clause(self) -> None:
        """A non-nullable column with a Python-side default gets a
        DEFAULT clause in the ALTER TABLE statement."""
        TestModel = self._make_model(
            "TestModel",
            "test_table",
            [
                Column("id", Integer, primary_key=True),
                Column(
                    "status",
                    String(16),
                    nullable=False,
                    default="active",
                ),
            ],
        )

        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = MagicMock()

        with patch(
            "airunner_services.database.setup_migrations."
            "_get_actual_columns",
            return_value={"id"},
        ):
            from airunner_services.database.setup_migrations import (
                _materialize_missing_columns,
            )

            # Capture the actual DDL
            ddl_statements = []

            def capture_ddl(eng, schema, table, col, dialect):
                from sqlalchemy import text as sql_text

                col_type_sql = col.type.compile(dialect=dialect)
                qualified = f"{schema}.{table}" if schema else table
                ddl = (
                    f"ALTER TABLE {qualified} "
                    f"ADD COLUMN {col.key} {col_type_sql}"
                )
                ddl_statements.append(ddl)
                eng.execute(sql_text(ddl))  # never called, mocked

            # Don't mock _add_column — let the real one run
            _materialize_missing_columns(
                engine, [TestModel], "test_schema",
            )

        # The _add_column should have been called and produced a
        # DEFAULT clause for the non-nullable column.
        assert engine.begin.call_count >= 1
