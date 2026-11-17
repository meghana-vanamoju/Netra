# DNS E2E Validation

Milestone 9.0 replaced the earlier synthetic-only status. See
[HARDWARE_TEST_RESULTS.md](HARDWARE_TEST_RESULTS.md) for the real AdGuard Home
lab evidence and [ADGUARD_HOME_INTEGRATION.md](ADGUARD_HOME_INTEGRATION.md) for
configuration and capability boundaries.

Summary of verified behavior:

- Authenticated AdGuard Home v0.107.50 API access on `http://127.0.0.1:3001`.
- Real query-log retrieval: 19 events, 19 unique domains, seven categories;
  repeated sync inserted 0 duplicates.
- Provider outage produced HTTP 503 on sync and `unreachable` status; restart
  restored `healthy` and data retrieval.
- Consent-gated rule application, query-log verification, and snapshot rollback
  were exercised against the lab with real filtered DNS responses.
- Automated tests additionally cover mocked unauthorized, timeout,
  unreachable, malformed, unsupported API, empty log, Pi-hole switching, and
  recovery paths.

Synthetic fixtures still exist for the legacy demo script and are labeled
`synthetic-demo`; they were not used for the physical counts above.
