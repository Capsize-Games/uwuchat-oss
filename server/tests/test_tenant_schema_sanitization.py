"""Regression tests for security finding #9 — tenant SQL identifier sanitization.

Verifies that malicious/malformed tenant claims are safely sanitized
into valid Postgres schema names and cannot alter the ``SET LOCAL
search_path`` statement's meaning.
"""

from __future__ import annotations

from airunner_services.data.tenant import tenant_schema_for_key


class TestTenantSchemaSanitization:
    """A malformed tenant key must never produce an unsafe schema name.

    ``tenant_schema_for_key`` is used to build ``SET LOCAL search_path``
    DDL.  Even though the key is regex-sanitised, this test pins the
    behaviour so a future refactor cannot accidentally introduce an
    injection vector.
    """

    def test_normal_key_produces_expected_schema(self) -> None:
        schema = tenant_schema_for_key("user_abc123")
        assert schema == "tenant_user_abc123"

    def test_key_with_semicolons_is_sanitized(self) -> None:
        """SQL injection attempt via semicolons is neutralised."""
        schema = tenant_schema_for_key("user; DROP SCHEMA public CASCADE;")
        assert ";" not in schema
        assert "DROP" not in schema
        # Semicolons and spaces become underscores; the trailing
        # strip('_') call removes the final underscore.
        assert schema == "tenant_user_drop_schema_public_cascade"

    def test_key_with_sql_keywords_is_sanitized(self) -> None:
        """SQL keywords in tenant key cannot alter query meaning."""
        schema = tenant_schema_for_key(
            "user UNION SELECT * FROM accounts"
        )
        assert "UNION" not in schema.upper() or "_union_" in schema.lower()
        assert schema.startswith("tenant_")

    def test_key_with_whitespace_is_sanitized(self) -> None:
        """Whitespace is converted to underscores."""
        schema = tenant_schema_for_key("my tenant key")
        assert " " not in schema
        assert schema == "tenant_my_tenant_key"

    def test_key_with_special_chars_is_sanitized(self) -> None:
        """Non-alphanumeric chars are replaced."""
        schema = tenant_schema_for_key("tenant$%^&*(){}|")
        assert schema.startswith("tenant_")

    def test_empty_key_falls_back_to_anonymous(self) -> None:
        schema = tenant_schema_for_key("")
        assert schema == "tenant_anonymous"

    def test_none_key_falls_back_to_anonymous(self) -> None:
        schema = tenant_schema_for_key(None)
        assert schema == "tenant_anonymous"

    def test_uuid_key_uses_compact_form(self) -> None:
        """UUID keys use the no-dash hex form for readability."""
        schema = tenant_schema_for_key(
            "550e8400-e29b-41d4-a716-446655440000"
        )
        # The UUID regex strips dashes
        assert "-" not in schema
        assert schema == (
            "tenant_550e8400e29b41d4a716446655440000"
        )

    def test_mixed_case_is_lowercased(self) -> None:
        schema = tenant_schema_for_key("MyTenant_ABC")
        assert schema == "tenant_mytenant_abc"
        assert schema.islower()

    def test_trailing_underscore_is_stripped(self) -> None:
        """The strip('_') call avoids double underscores."""
        schema = tenant_schema_for_key("key!!!")
        assert schema == "tenant_key"
        assert schema.endswith("key")

    def test_schema_prefix_can_be_overridden(self) -> None:
        """The schema prefix is configurable via contextvar."""
        from airunner_services.data.tenant import (
            reset_tenant_schema_prefix,
            set_tenant_schema_prefix,
        )

        tok = set_tenant_schema_prefix("cust_")
        try:
            schema = tenant_schema_for_key("abc123")
            assert schema == "cust_abc123"
        finally:
            reset_tenant_schema_prefix(tok)
