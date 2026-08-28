# mcp2vql

MCP server exposing VQL query, conversion, image diagnosis and mutation tools.

Queries, UI detection, comparison and NL-to-DSL conversion remain read-only.
Patching, DSL execution, metadata writes and `vql_apply_nl(..., execute=true)`
are disabled unless the server operator sets `VQL_MCP_ALLOW_MUTATION=1` for
trusted MCP clients. Natural-language application defaults to `execute=false`.
