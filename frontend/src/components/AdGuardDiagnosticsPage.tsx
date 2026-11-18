import { useCallback, useEffect, useState } from "react";
import {
  getAdGuardDiagnostics,
  getDnsEvents,
  getDnsProviderFiltering,
  getDnsProviderStatus,
  refreshDnsFilters,
  setDnsFilteringRule,
  syncDnsEvents,
} from "../api";
import { useNetworkContext } from "../NetworkContext";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import type {
  AdGuardDiagnostics,
  ApiError,
  DnsEvent,
  DnsProviderStatus,
} from "../types";

const TEST_DOMAIN = "netra-test.blocked.invalid";
const TEST_RULE = `||${TEST_DOMAIN}^`;

type ProviderFiltering = { enabled: boolean; user_rules: string[]; filter_count: number | null };

function toApiError(error: unknown): ApiError {
  return error instanceof Error ? error : new Error(String(error));
}

function providerLabel(state: string | undefined) {
  return state || "unknown";
}

export function AdGuardDiagnosticsPage() {
  const { selectedSubnet, selectedDeviceId } = useNetworkContext();
  const [diagnostics, setDiagnostics] = useState<AdGuardDiagnostics | null>(null);
  const [provider, setProvider] = useState<DnsProviderStatus | null>(null);
  const [filtering, setFiltering] = useState<ProviderFiltering | null>(null);
  const [events, setEvents] = useState<DnsEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState("");
  const [testConfirmed, setTestConfirmed] = useState(false);
  const [rulePresent, setRulePresent] = useState<boolean | null>(null);
  const [blockEvidence, setBlockEvidence] = useState<DnsEvent | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [diagnosticsResult, providerResult, filteringResult] = await Promise.all([
        getAdGuardDiagnostics(selectedSubnet ?? undefined, selectedDeviceId ?? undefined),
        getDnsProviderStatus(),
        getDnsProviderFiltering().catch(() => null),
      ]);
      setDiagnostics(diagnosticsResult);
      setProvider(providerResult);
      setFiltering(filteringResult);
      if (filteringResult) {
        setRulePresent(filteringResult.user_rules.includes(TEST_RULE));
      }
    } catch (loadError) {
      setError(toApiError(loadError));
    } finally {
      setLoading(false);
    }
  }, [selectedDeviceId, selectedSubnet]);

  useEffect(() => {
    void load();
  }, [load]);

  const checkConnectivity = async () => {
    setBusy("Checking provider connectivity…");
    setMessage("");
    await load();
    setBusy("");
    setMessage("Connectivity check complete. See provider state below.");
  };

  const addTestRule = async () => {
    if (!testConfirmed) return;
    setBusy("Adding temporary rule…");
    setError(null);
    setMessage("");
    try {
      const result = await setDnsFilteringRule(TEST_DOMAIN, "block", true);
      setMessage(`Temporary rule applied through provider: ${String(result.status ?? "applied")}.`);
      const after = await getDnsProviderFiltering();
      setFiltering(after);
      setRulePresent(after.user_rules.includes(TEST_RULE));
    } catch (ruleError) {
      setError(toApiError(ruleError));
    } finally {
      setBusy("");
    }
  };

  const verifyQueryLog = async () => {
    setBusy("Syncing and checking query log…");
    setError(null);
    try {
      const sync = await syncDnsEvents();
      const rows = await getDnsEvents({ limit: 100, domain: TEST_DOMAIN });
      setEvents(rows);
      const blocked = rows.find((event) => event.blocked === true) ?? null;
      setBlockEvidence(blocked);
      setMessage(
        `Synced ${sync.fetched} provider events; ${rows.length} matching stored event(s) for ${TEST_DOMAIN}.`,
      );
    } catch (logError) {
      setError(toApiError(logError));
    } finally {
      setBusy("");
    }
  };

  const removeTestRule = async () => {
    if (!testConfirmed) return;
    setBusy("Removing temporary rule…");
    setError(null);
    try {
      const result = await setDnsFilteringRule(TEST_DOMAIN, "unblock", true);
      setMessage(`Temporary rule removal requested: ${String(result.status ?? "removed")}.`);
      const after = await getDnsProviderFiltering();
      setFiltering(after);
      setRulePresent(after.user_rules.includes(TEST_RULE));
    } catch (ruleError) {
      setError(toApiError(ruleError));
    } finally {
      setBusy("");
    }
  };

  const reloadFilters = async () => {
    setBusy("Requesting provider filter refresh…");
    setError(null);
    try {
      const result = await refreshDnsFilters();
      setMessage(String(result.status ?? "Filter refresh requested."));
    } catch (refreshError) {
      setError(toApiError(refreshError));
    } finally {
      setBusy("");
    }
  };

  return (
    <LocalizedTree>
      <section className="diagnostics-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> PROVIDER DIAGNOSTICS</div>
            <h1>AdGuard <span>validation.</span></h1>
            <p className="page-description">
              Evidence-based provider diagnostics and a reversible test procedure. Netra does not change router DHCP or DNS settings.
            </p>
          </div>
          <button className="refresh-button" type="button" onClick={() => void checkConnectivity()} disabled={loading || Boolean(busy)}>
            <Icon name="refresh" size={16} />
            <span>Check connectivity</span>
          </button>
        </div>

        <div className="diagnostics-scope-note">
          <Icon name="alert" size={16} />
          <span>
            Only provider-level functionality is verified here. Router-wide and client-level DNS enforcement require independent DHCP/DNS and query-log evidence.
          </span>
        </div>

        {error && <div className="panel-state error-state"><ErrorMessage error={error} /></div>}
        {message && <div className="panel-state success-state" role="status">{message}</div>}
        {loading && <div className="panel-state"><LoadingValue /><span>Loading provider diagnostics…</span></div>}

        {!loading && diagnostics && (
          <>
            <section className="metric-grid">
              <article className="metric-card">
                <div className="metric-top"><span className="metric-label">PROVIDER STATE</span><span className="metric-icon violet"><Icon name="pulse" size={17} /></span></div>
                <div className="metric-value metric-status">{providerLabel(diagnostics.provider.state)}</div>
                <div className="metric-foot"><span>{diagnostics.provider.provider ?? "No provider"}</span></div>
              </article>
              <article className="metric-card">
                <div className="metric-top"><span className="metric-label">AUTHENTICATION</span><span className="metric-icon green"><Icon name="lock" size={17} /></span></div>
                <div className="metric-value metric-status">{diagnostics.provider.authentication ?? "unknown"}</div>
                <div className="metric-foot"><span>No credentials are displayed</span></div>
              </article>
              <article className="metric-card">
                <div className="metric-top"><span className="metric-label">FILTERING</span><span className="metric-icon amber"><Icon name="shield" size={17} /></span></div>
                <div className="metric-value metric-status">
                  {diagnostics.filtering.data ? (diagnostics.filtering.data.enabled ? "ENABLED" : "DISABLED") : "UNAVAILABLE"}
                </div>
                <div className="metric-foot"><span>{diagnostics.filtering.data?.filter_count ?? "—"} filter lists</span></div>
              </article>
              <article className="metric-card">
                <div className="metric-top"><span className="metric-label">ROUTER DNS</span><span className="metric-icon blue"><Icon name="router" size={17} /></span></div>
                <div className="metric-value metric-status">NOT VERIFIED</div>
                <div className="metric-foot"><span>Gateway {diagnostics.router.gateway ?? "unknown"}</span></div>
              </article>
            </section>

            <section className="detail-grid">
              <article className="panel">
                <div className="panel-header"><div><div className="panel-kicker">PROVIDER EVIDENCE</div><h2>Connectivity and query log</h2></div></div>
                <div className="dashboard-fact-list">
                  <div><span>Version</span><strong>{diagnostics.provider.version ?? "unknown"}</strong></div>
                  <div><span>Interface</span><strong data-no-translate="true">{diagnostics.router.interface ?? "unknown"}</strong></div>
                  <div><span>Latest query timestamp</span><strong>{diagnostics.query_log.latest_timestamp ?? "none"}</strong></div>
                  <div><span>Recorded queries</span><strong>{diagnostics.query_log.recorded_events}</strong></div>
                  <div><span>Linked to inventory</span><strong>{diagnostics.query_log.linked_events}</strong></div>
                  <div><span>Selected clients identifiable</span><strong>{diagnostics.query_log.clients_identifiable ? "Yes" : "No"}</strong></div>
                </div>
                <p className="panel-footer-note">{diagnostics.router.note}</p>
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div><div className="panel-kicker">USER RULES</div><h2>Configured filtering rules</h2></div>
                  <span className="read-only-tag">{filtering?.user_rules.length ?? 0} RULES</span>
                </div>
                {!filtering ? (
                  <div className="empty-state"><span className="empty-icon"><Icon name="alert" size={20} /></span><strong>Rules unavailable</strong></div>
                ) : filtering.user_rules.length === 0 ? (
                  <div className="empty-state"><span className="empty-icon"><Icon name="shield" size={20} /></span><strong>No user rules</strong></div>
                ) : (
                  <ul className="diagnostics-rule-list">
                    {filtering.user_rules.map((rule) => (
                      <li data-no-translate="true" key={rule}>{rule}</li>
                    ))}
                  </ul>
                )}
                <button className="secondary-button" type="button" onClick={() => void reloadFilters()} disabled={Boolean(busy)}>
                  Refresh provider filter lists
                </button>
              </article>
            </section>

            <section className="panel diagnostics-test-panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">REVERSIBLE VALIDATION</div>
                  <h2>Safe AdGuard test procedure</h2>
                </div>
                <span className="read-only-tag">TEST DOMAIN: {TEST_DOMAIN}</span>
              </div>
              <p>
                This uses a reserved, non-common test domain. Netra records a snapshot before adding the rule and never changes router DNS settings.
              </p>
              <ol className="diagnostics-steps">
                <li><strong>Check connectivity.</strong> Use the button above; provider state must be healthy.</li>
                <li>
                  <strong>Add temporary block rule.</strong>
                  <label>
                    <input type="checkbox" checked={testConfirmed} onChange={(event) => setTestConfirmed(event.target.checked)} />
                    I confirm adding and later removing the temporary test rule.
                  </label>
                  <button className="secondary-button" type="button" onClick={() => void addTestRule()} disabled={!testConfirmed || Boolean(busy)}>
                    Add temporary rule
                  </button>
                </li>
                <li>
                  <strong>Verify rule in provider.</strong>
                  <span>{rulePresent === null ? "Not checked" : rulePresent ? `Present: ${TEST_RULE}` : `Not present: ${TEST_RULE}`}</span>
                </li>
                <li>
                  <strong>Query the test domain from a client.</strong>
                  <pre>{`dig @<ADGUARD_IP> ${TEST_DOMAIN} +short\n# Expected while the rule is active: 0.0.0.0 or the configured block response`}</pre>
                </li>
                <li>
                  <strong>Verify the query in AdGuard's log.</strong>
                  <button className="secondary-button" type="button" onClick={() => void verifyQueryLog()} disabled={Boolean(busy)}>
                    Sync and check query log
                  </button>
                  <span>{blockEvidence ? `Blocked evidence at ${blockEvidence.timestamp}` : "No blocked query evidence yet"}</span>
                </li>
                <li><strong>Verify client response.</strong> The client's <code>dig</code> output should match the provider's blocked response. No response means the client is not using AdGuard.</li>
                <li>
                  <strong>Remove the temporary rule.</strong>
                  <button className="secondary-button" type="button" onClick={() => void removeTestRule()} disabled={!testConfirmed || Boolean(busy)}>
                    Remove temporary rule
                  </button>
                </li>
                <li>
                  <strong>Verify normal resolution restored.</strong>
                  <pre>{`dig @<ADGUARD_IP> ${TEST_DOMAIN} +short\n# The test domain is reserved and should not resolve to a real service.\n# Confirm the temporary rule is absent and the client query is no longer blocked.`}</pre>
                </li>
              </ol>
              {events.length > 0 && (
                <div className="inventory-table-wrap">
                  <table className="device-table">
                    <thead><tr><th>TIME</th><th>DOMAIN</th><th>CLIENT</th><th>STATUS</th><th>REASON</th></tr></thead>
                    <tbody>
                      {events.map((event) => (
                        <tr key={event.id}>
                          <td>{event.timestamp}</td>
                          <td data-no-translate="true">{event.domain}</td>
                          <td>{event.client ?? "unknown"}</td>
                          <td>{event.blocked === null || event.blocked === undefined ? "Unknown" : event.blocked ? "Blocked" : "Allowed"}</td>
                          <td>{event.reason ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </section>
    </LocalizedTree>
  );
}
