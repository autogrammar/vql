"""Safety tests for mcp2vql."""

import pytest

from mcp2vql.server import _require_mutation


def test_mcp_mutations_require_operator_capability(monkeypatch) -> None:
    monkeypatch.delenv("VQL_MCP_ALLOW_MUTATION", raising=False)
    with pytest.raises(PermissionError, match="VQL_MCP_ALLOW_MUTATION"):
        _require_mutation("vql_patch")

    monkeypatch.setenv("VQL_MCP_ALLOW_MUTATION", "1")
    _require_mutation("vql_patch")
