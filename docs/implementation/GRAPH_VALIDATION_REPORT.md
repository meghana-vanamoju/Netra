# Graph Validation Report

## Orbit
- DB: ~/.orbit/graph.duckdb
- Indexed: 2026-11-17 11:02 UTC; manifest status `indexed`
- Indexed files: 126 (95 parseable)
- Definitions: 1,111
- Imported symbols: 548
- Relationships: 2,815
- Skipped files: 0
- Errored files: 0
- Repository map regenerated after final indexing with `orbit repo-map --repo .. overview`.
- Actual Orbit MCP stdio retrieval completed against this index: initialized `orbit-local` 0.88.1, called `run_sql`, and retrieved the Netra manifest/statistics plus `is_authorized_router_ip`, `get_authorized_networks`, `AdGuardHomeAdapter`, and `merge_devices`.
- The index was built from the final worktree and records base HEAD
	`da29514532922569e3a9ec865cd1899c22f29dd0`; commit metadata was not yet
	updated when this report was generated.

## Logseq
- Local graph: logseq-graph/
- Pages updated: Netra, Netra Architecture; added Router Integration.
- MCP retrieval: not verified. Tool discovery returned no Logseq MCP retrieval
	tool in this environment, so no successful Logseq retrieval is claimed.
- Local page content was read from the workspace; that is file verification,
	not MCP retrieval.

## Commands
- `orbit index .. --stats`
- `orbit repo-map --repo .. overview`
- Orbit MCP `tools/call` -> `run_sql` (manifest, counts, symbol lookup)
