import { useCallback, useEffect, useState } from "react";
import {
  getAudit,
  getAuditFindings,
  getAuditReports,
  getBackendCapabilities,
  getDatabaseHealth,
  getDevices,
  getDnsSummary,
  getHealth,
} from "./api";
import { AppShell } from "./components/AppShell";
import type { AppPage } from "./components/AppShell";
import { DeviceInventoryPage } from "./components/DeviceInventoryPage";
import { DiscoveryPage } from "./components/DiscoveryPage";
import { DnsAnalyticsPage } from "./components/DnsAnalyticsPage";
import { PrivacyAuditPage } from "./components/PrivacyAuditPage";
import { PolicyPlanningPage } from "./components/PolicyPlanningPage";
import { EnforcementRecoveryPage } from "./components/EnforcementRecoveryPage";
import { SettingsBackendPage } from "./components/SettingsBackendPage";
import { ErrorMessage, Icon, LoadingValue } from "./components/ui";
import type {
  ApiError,
  AuditDetail,
  AuditFinding,
  AuditReport,
  BackendCapabilities,
  Device,
  DnsSummary,
  HealthResponse,
  ResourceState,
} from "./types";

type DashboardData = {
  health: ResourceState<HealthResponse>;
  database: ResourceState<{ status: string }>;
  devices: ResourceState<Device[]>;
  dns: ResourceState<DnsSummary>;
  audit: ResourceState<{
    report: AuditDetail & { created_at: string };
    findings: AuditFinding[];
  } | null>;
  capabilities: ResourceState<BackendCapabilities>;
};

const initialState: DashboardData = {
  health: { status: "loading" },
  database: { status: "loading" },
  devices: { status: "loading" },
  dns: { status: "loading" },
  audit: { status: "loading" },
  capabilities: { status: "loading" },
};

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function toApiError(error: unknown): ApiError {
  if (error instanceof Error) {
    return error;
  }
  return new Error(`Unexpected API error: ${String(error)}`);
}

function pageFromHash(): AppPage {
  if (window.location.hash === "#devices") {
    return "devices";
  }
  if (window.location.hash === "#discovery") {
    return "discovery";
  }
  if (window.location.hash === "#dns-activity") {
    return "dns-activity";
  }
  if (window.location.hash === "#privacy-audit") {
    return "privacy-audit";
  }
  if (window.location.hash === "#policy-planning") {
    return "policy-planning";
  }
  if (window.location.hash === "#enforcement-recovery") {
    return "enforcement-recovery";
  }
  if (window.location.hash === "#settings-backend") {
    return "settings-backend";
  }
  return "overview";
}

function App() {
  const [data, setData] = useState<DashboardData>(initialState);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState<AppPage>(pageFromHash);

  const navigate = useCallback((nextPage: AppPage) => {
    const hash =
      nextPage === "dns-activity" ? "#dns-activity" : `#${nextPage}`;
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setPage(nextPage);
  }, []);

  const loadDashboard = useCallback(async () => {
    setRefreshing(true);

    const [health, database, devices, dns, auditList, capabilities] =
      await Promise.allSettled([
        getHealth(),
        getDatabaseHealth(),
        getDevices(),
        getDnsSummary(),
        getAuditReports(),
        getBackendCapabilities(),
      ]);

    const audit =
      auditList.status === "fulfilled" && auditList.value.length > 0
        ? await Promise.allSettled([
            getAudit(auditList.value[0].id),
            getAuditFindings(auditList.value[0].id),
          ])
        : null;

    setData({
      health:
        health.status === "fulfilled"
          ? { status: "ready", data: health.value }
          : { status: "error", error: toApiError(health.reason) },
      database:
        database.status === "fulfilled"
          ? { status: "ready", data: database.value }
          : { status: "error", error: toApiError(database.reason) },
      devices:
        devices.status === "fulfilled"
          ? { status: "ready", data: devices.value }
          : { status: "error", error: toApiError(devices.reason) },
      dns:
        dns.status === "fulfilled"
          ? { status: "ready", data: dns.value }
          : { status: "error", error: toApiError(dns.reason) },
      audit:
        auditList.status === "rejected"
          ? { status: "error", error: toApiError(auditList.reason) }
          : auditList.value.length === 0
            ? { status: "ready", data: null }
            : audit?.[0].status === "fulfilled" && audit[1].status === "fulfilled"
              ? {
                  status: "ready",
                  data: {
                    report: {
                      ...audit[0].value,
                      created_at: auditList.value[0].created_at,
                    },
                    findings: audit[1].value,
                  },
                }
                : {
                    status: "error",
                    error: toApiError(
                      audit?.find((result) => result.status === "rejected")?.reason ??
                        new Error("Unable to load the latest audit."),
                    ),
                  },
      capabilities:
        capabilities.status === "fulfilled"
          ? { status: "ready", data: capabilities.value }
          : { status: "error", error: toApiError(capabilities.reason) },
    });
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    const syncPage = () => setPage(pageFromHash());
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  const apiOnline =
    data.health.status === "ready" && data.health.data.status === "ok";
  const apiChecking = data.health.status === "loading";
  const latestAudit =
    data.audit.status === "ready" ? data.audit.data : undefined;
  const categoryEntries =
    data.dns.status === "ready"
      ? Object.entries(data.dns.data.by_category).sort((a, b) => b[1] - a[1])
      : [];
  const totalCategoryEvents = categoryEntries.reduce(
    (total, [, count]) => total + count,
    0,
  );
  const findings = latestAudit?.findings ?? [];
  const mediumOrHigherFindings = findings.filter((finding) =>
    ["high", "medium", "critical"].includes(finding.severity.toLowerCase()),
  ).length;

  return (
    <AppShell
      apiOnline={apiOnline}
      apiChecking={apiChecking}
      auditCount={latestAudit ? findings.length : null}
      page={page}
      onNavigate={navigate}
    >
      {page === "devices" ? (
        <DeviceInventoryPage />
      ) : page === "discovery" ? (
        <DiscoveryPage />
      ) : page === "dns-activity" ? (
        <DnsAnalyticsPage />
      ) : page === "privacy-audit" ? (
        <PrivacyAuditPage />
      ) : page === "policy-planning" ? (
        <PolicyPlanningPage />
      ) : page === "enforcement-recovery" ? (
        <EnforcementRecoveryPage />
      ) : page === "settings-backend" ? (
        <SettingsBackendPage />
      ) : (
      <>
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> NETWORK OVERVIEW</div>
              <h1>Your network, <span>in focus.</span></h1>
              <p className="page-description">A clear view of the devices and activity on your home network.</p>
            </div>
            <button
              className="refresh-button"
              onClick={() => void loadDashboard()}
              disabled={refreshing}
              type="button"
            >
              <Icon name="refresh" size={16} />
              <span>{refreshing ? "Refreshing…" : "Refresh data"}</span>
            </button>
          </div>

          <section className="status-banner" aria-label="Backend status">
            <div className={`status-symbol${apiOnline ? " healthy" : data.health.status === "loading" ? " pending" : " danger"}`}>
              <Icon name={apiOnline ? "check" : data.health.status === "loading" ? "pulse" : "alert"} size={18} />
            </div>
            <div className="status-copy">
              <strong>
                {data.health.status === "loading"
                  ? "Connecting to your Netra backend"
                  : apiOnline
                    ? "Netra backend is reachable"
                    : "Could not reach the Netra backend"}
              </strong>
              <span>
                {data.health.status === "error"
                  ? "Check that the backend is running and the API URL is correct."
                  : data.database.status === "error"
                    ? "The API responded, but its database health check failed."
                    : "Dashboard values below are fetched live from your configured backend."}
              </span>
            </div>
            <div className={`status-badge${apiOnline ? " good" : data.health.status === "loading" ? " waiting" : " bad"}`}>
              {data.health.status === "loading" ? "CHECKING" : apiOnline ? "CONNECTED" : "OFFLINE"}
            </div>
          </section>

          <section className="metric-grid" aria-label="Network summary">
            <article className="metric-card" id="devices">
              <div className="metric-top">
                <span className="metric-label">DEVICES IN INVENTORY</span>
                <span className="metric-icon blue"><Icon name="devices" size={18} /></span>
              </div>
              <div className="metric-value">
                {data.devices.status === "ready" ? formatNumber(data.devices.data.length) : data.devices.status === "loading" ? <LoadingValue /> : "—"}
              </div>
              <div className="metric-foot">
                <span>{data.devices.status === "ready" ? data.devices.data.length === 200 ? "At least 200 devices returned · API page limit" : "Devices returned by inventory" : data.devices.status === "error" ? "Inventory unavailable" : "Loading inventory"}</span>
                <span className="metric-foot-icon"><Icon name="arrow" size={14} /></span>
              </div>
              {data.devices.status === "error" && <ErrorMessage error={data.devices.error} />}
            </article>

            <article className="metric-card" id="dns-activity">
              <div className="metric-top">
                <span className="metric-label">DNS QUERIES OBSERVED</span>
                <span className="metric-icon violet"><Icon name="pulse" size={18} /></span>
              </div>
              <div className="metric-value">
                {data.dns.status === "ready" ? formatNumber(data.dns.data.total) : data.dns.status === "loading" ? <LoadingValue /> : "—"}
              </div>
              <div className="metric-foot">
                <span>{data.dns.status === "ready" ? `${formatNumber(data.dns.data.unique_domains)} unique domains` : data.dns.status === "error" ? "DNS analytics unavailable" : "Loading analytics"}</span>
                <span className="metric-foot-icon"><Icon name="arrow" size={14} /></span>
              </div>
              {data.dns.status === "error" && <ErrorMessage error={data.dns.error} />}
            </article>

            <article className="metric-card" id="privacy-audit">
              <div className="metric-top">
                <span className="metric-label">LATEST AUDIT FINDINGS</span>
                <span className="metric-icon amber"><Icon name="shield" size={18} /></span>
              </div>
              <div className="metric-value">
                {data.audit.status === "ready"
                  ? latestAudit
                    ? formatNumber(findings.length)
                    : "—"
                  : data.audit.status === "loading" ? <LoadingValue /> : "—"}
              </div>
              <div className="metric-foot">
                <span>
                  {data.audit.status === "error"
                    ? "Audit history unavailable"
                    : latestAudit
                      ? `From audit #${latestAudit.report.id}`
                      : data.audit.status === "loading"
                        ? "Checking audit history"
                        : "No audit has been run"}
                </span>
                <span className="metric-foot-icon"><Icon name="arrow" size={14} /></span>
              </div>
              {data.audit.status === "error" && <ErrorMessage error={data.audit.error} />}
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span className="metric-label">DATABASE STATUS</span>
                <span className="metric-icon green"><Icon name="lock" size={18} /></span>
              </div>
              <div className="metric-value metric-status">
                {data.database.status === "ready" ? data.database.data.status.toUpperCase() : data.database.status === "loading" ? <LoadingValue /> : "—"}
              </div>
              <div className="metric-foot">
                <span>{data.database.status === "ready" ? "Backend database health" : data.database.status === "error" ? "Health check unavailable" : "Checking database"}</span>
                <span className={`mini-status${data.database.status === "ready" ? " is-good" : ""}`} />
              </div>
              {data.database.status === "error" && <ErrorMessage error={data.database.error} />}
            </article>
          </section>

          <section className="detail-grid">
            <article className="panel dns-panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">TRAFFIC BREAKDOWN</div>
                  <h2>DNS activity</h2>
                </div>
                <span className="live-tag"><span /> LIVE DATA</span>
              </div>
              {data.dns.status === "loading" ? (
                <div className="panel-state"><LoadingValue /><span>Loading DNS analytics…</span></div>
              ) : data.dns.status === "error" ? (
                <div className="panel-state error-state"><ErrorMessage error={data.dns.error} /></div>
              ) : categoryEntries.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon"><Icon name="pulse" size={21} /></span>
                  <strong>No DNS activity yet</strong>
                  <span>When DNS events are recorded, their categories will appear here.</span>
                </div>
              ) : (
                <div className="category-list">
                  {categoryEntries.map(([category, count], index) => (
                    <div className="category-row" key={category}>
                      <div className="category-heading">
                        <span className={`category-dot category-${index % 4}`} />
                        <span className="category-name">{category}</span>
                        <span className="category-count">{formatNumber(count)}</span>
                        <span className="category-percent">{totalCategoryEvents ? Math.round((count / totalCategoryEvents) * 100) : 0}%</span>
                      </div>
                      <div className="category-track">
                        <span className={`category-bar category-${index % 4}`} style={{ width: `${totalCategoryEvents ? (count / totalCategoryEvents) * 100 : 0}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="panel-footer">
                <span>Categories from recorded DNS events</span>
                <span className="footer-note"><Icon name="lock" size={13} /> Read-only</span>
              </div>
            </article>

            <article className="panel audit-panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">PRIVACY &amp; SECURITY</div>
                  <h2>Audit overview</h2>
                </div>
                <span className="read-only-tag"><Icon name="lock" size={13} /> READ-ONLY</span>
              </div>
              {data.audit.status === "loading" ? (
                <div className="panel-state"><LoadingValue /><span>Loading audit history…</span></div>
              ) : data.audit.status === "error" ? (
                <div className="panel-state error-state"><ErrorMessage error={data.audit.error} /></div>
              ) : latestAudit ? (
                <>
                  <div className="audit-summary">
                    <div className={`audit-summary-icon${mediumOrHigherFindings ? " has-findings" : ""}`}>
                      <Icon name={mediumOrHigherFindings ? "alert" : "check"} size={20} />
                    </div>
                    <div>
                      <strong>{findings.length === 0 ? "No findings reported" : `${findings.length} finding${findings.length === 1 ? "" : "s"} in latest audit`}</strong>
                      <span>
                        {mediumOrHigherFindings
                          ? `${mediumOrHigherFindings} medium-or-higher severity`
                          : `Audit #${latestAudit.report.id} · ${new Date(latestAudit.report.created_at).toLocaleString()}`}
                      </span>
                    </div>
                  </div>
                  {findings.length > 0 && (
                    <div className="finding-list">
                      {findings.slice(0, 3).map((finding) => (
                        <div className="finding-row" key={finding.id}>
                          <span className={`severity-dot severity-${finding.severity.toLowerCase()}`} />
                          <span>{finding.title}</span>
                          <span className="finding-severity">{finding.severity}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="audit-disclaimer">This is the latest saved audit, not a live scan. No policies are applied by this dashboard.</div>
                </>
              ) : (
                <div className="empty-state audit-empty">
                  <span className="empty-icon"><Icon name="shield" size={21} /></span>
                  <strong>No saved audit yet</strong>
                  <span>Netra has not reported an audit for this network.</span>
                </div>
              )}
            </article>
          </section>

          <section className="bottom-grid">
            <article className="panel device-panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">NETWORK INVENTORY</div>
                  <h2>Recently seen devices</h2>
                </div>
                <a className="text-link" href="#devices">Device inventory <Icon name="arrow" size={14} /></a>
              </div>
              {data.devices.status === "loading" ? (
                <div className="panel-state"><LoadingValue /><span>Loading device inventory…</span></div>
              ) : data.devices.status === "error" ? (
                <div className="panel-state error-state"><ErrorMessage error={data.devices.error} /></div>
              ) : data.devices.data.length === 0 ? (
                <div className="empty-state compact-empty">
                  <span className="empty-icon"><Icon name="devices" size={19} /></span>
                  <strong>No devices registered</strong>
                  <span>Devices will appear here once they are added to the inventory.</span>
                </div>
              ) : (
                <div className="device-table-wrap">
                  <table className="device-table">
                    <thead><tr><th>DEVICE</th><th>IP ADDRESS</th><th>LAST SEEN</th><th>STATUS</th></tr></thead>
                    <tbody>
                      {data.devices.data.slice(0, 5).map((device) => (
                        <tr key={device.id}>
                          <td>
                            <span className="device-name-cell">
                              <span className="device-avatar"><Icon name="devices" size={16} /></span>
                              <span><strong>{device.hostname || device.vendor || "Unknown device"}</strong><small>{device.vendor || device.discovery_source || "Device"}</small></span>
                            </span>
                          </td>
                          <td className="ip-address">{device.ip_address}</td>
                          <td className="last-seen">{new Date(device.last_seen).toLocaleString()}</td>
                          <td><span className="device-status"><span /> In inventory</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {data.devices.data.length > 5 && (
                    <div className="table-overflow-note">
                      Showing 5 of {data.devices.data.length === 200 ? "at least " : ""}
                      {formatNumber(data.devices.data.length)} devices returned.
                    </div>
                  )}
                </div>
              )}
            </article>

            <article className="panel connection-panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">INTEGRATION STATUS</div>
                  <h2>Backend connection</h2>
                </div>
                <span className="metric-icon green"><Icon name="router" size={17} /></span>
              </div>
              <div className="integration-row">
                <span className="integration-name"><Icon name="router" size={17} /> Netra API</span>
                <span className={`integration-status ${apiOnline ? "is-good" : data.health.status === "loading" ? "is-waiting" : "is-bad"}`}>
                  <span />{data.health.status === "loading" ? "Checking" : apiOnline ? "Connected" : "Unavailable"}
                </span>
              </div>
              <div className="integration-row">
                <span className="integration-name"><Icon name="lock" size={17} /> Database</span>
                <span className={`integration-status ${data.database.status === "ready" ? "is-good" : data.database.status === "loading" ? "is-waiting" : "is-bad"}`}>
                  <span />{data.database.status === "ready" ? data.database.data.status : data.database.status === "loading" ? "Checking" : "Unavailable"}
                </span>
              </div>
              <div className="integration-row">
                <span className="integration-name"><Icon name="shield" size={17} /> DNS backend</span>
                <span className={`integration-status ${data.capabilities.status === "ready" && data.capabilities.data.available ? "is-good" : data.capabilities.status === "loading" ? "is-waiting" : ""}`}>
                  <span />{data.capabilities.status === "ready" ? data.capabilities.data.available ? "Configured" : "Not configured" : data.capabilities.status === "loading" ? "Checking" : "Unavailable"}
                </span>
              </div>
              {data.capabilities.status === "error" && <ErrorMessage error={data.capabilities.error} />}
              <div className="integration-note">
                {data.capabilities.status === "ready" && data.capabilities.data.configured_backend
                  ? `Configured backend: ${data.capabilities.data.configured_backend}. Configuration does not mean enforcement is active.`
                  : "A configured DNS backend is not required for read-only inventory and analytics."}
              </div>
            </article>
          </section>

          <footer className="page-footer">
            <span><span className="footer-brand-mark"><Icon name="router" size={14} /></span> NETRA <span className="footer-separator">·</span> SEE YOUR NETWORK CLEARLY. PROTECT IT SAFELY.</span>
            <span>Dashboard data is fetched from your backend. No demo data shown.</span>
          </footer>
      </>
      )}
    </AppShell>
  );
}

export default App;
