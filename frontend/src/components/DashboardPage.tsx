import { useCallback, useEffect, useState } from "react";
import { getDashboardSummary } from "../api";
import { useNetworkContext } from "../NetworkContext";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import type { ApiError, DashboardSummary, ResourceState } from "../types";

function toApiError(error: unknown): ApiError {
  return error instanceof Error ? error : new Error(String(error));
}

function number(value: number | null | undefined) {
  return typeof value === "number" ? new Intl.NumberFormat().format(value) : "—";
}

function bytes(value: number | null | undefined) {
  if (typeof value !== "number") return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function rate(value: number | null | undefined) {
  return typeof value === "number" ? `${bytes(value)}/s` : "No sample yet";
}

function formatTime(value: string | null | undefined) {
  if (!value) return "No scan recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function DashboardPage() {
  const { selectedSubnet, clearNetworkContext } = useNetworkContext();
  const [summary, setSummary] = useState<ResourceState<DashboardSummary>>({
    status: "loading",
  });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await getDashboardSummary(selectedSubnet ?? undefined);
      setSummary({ status: "ready", data });
    } catch (error) {
      setSummary({ status: "error", error: toApiError(error) });
    } finally {
      setRefreshing(false);
    }
  }, [selectedSubnet]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <LocalizedTree>
      <section className="dashboard-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> NETWORK OVERVIEW</div>
            <h1>Your network, <span>in focus.</span></h1>
            <p className="page-description">
              Live values from the Netra backend. Laptop-local measurements are labelled separately from router-wide protection.
            </p>
            {selectedSubnet && (
              <p className="muted-copy">
                Selected subnet: <span data-no-translate="true">{selectedSubnet}</span>
                <button type="button" className="secondary-button" onClick={() => clearNetworkContext()}>
                  Clear subnet
                </button>
              </p>
            )}
          </div>
          <button className="refresh-button" type="button" onClick={() => void load()} disabled={refreshing}>
            <Icon name="refresh" size={16} />
            <span>{refreshing ? "Refreshing…" : "Refresh data"}</span>
          </button>
        </div>

        {summary.status === "loading" && (
          <div className="panel-state"><LoadingValue /><span>Loading live dashboard data…</span></div>
        )}
        {summary.status === "error" && (
          <div className="panel-state error-state"><ErrorMessage error={summary.error} /></div>
        )}
        {summary.status === "ready" && (
          <>
            <section className="metric-grid" aria-label="Network summary">
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">DEVICES</span>
                  <span className="metric-icon blue"><Icon name="devices" size={18} /></span>
                </div>
                <div className="metric-value">{number(summary.data.devices.count)}</div>
                <div className="metric-foot"><span>{summary.data.devices.scope}</span></div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">DNS QUERIES</span>
                  <span className="metric-icon violet"><Icon name="pulse" size={18} /></span>
                </div>
                <div className="metric-value">{number(summary.data.dns.total)}</div>
                <div className="metric-foot">
                  <span>
                    {number(summary.data.dns.allowed)} allowed · {number(summary.data.dns.blocked)} blocked
                  </span>
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">BLOCK RATE</span>
                  <span className="metric-icon amber"><Icon name="shield" size={18} /></span>
                </div>
                <div className="metric-value">
                  {summary.data.dns.blocking_percentage === null
                    ? "Unknown"
                    : `${summary.data.dns.blocking_percentage.toFixed(1)}%`}
                </div>
                <div className="metric-foot">
                  <span>
                    Blocked / (allowed + blocked); {number(summary.data.dns.unknown_blocked_status)} unknown status
                  </span>
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">PRIVACY SCORE</span>
                  <span className="metric-icon green"><Icon name="shield" size={18} /></span>
                </div>
                <div className="metric-value">{number(summary.data.privacy.score)}</div>
                <div className="metric-foot">
                  <span>
                    {summary.data.privacy.latest_audit_id
                      ? `Latest audit #${summary.data.privacy.latest_audit_id}`
                      : "No audit recorded"}
                  </span>
                </div>
              </article>
            </section>

            <section className="detail-grid">
              <article className="panel">
                <div className="panel-header">
                  <div>
                    <div className="panel-kicker">DISCOVERY</div>
                    <h2>Coverage and last scan</h2>
                  </div>
                  <span className="read-only-tag">
                    {summary.data.discovery.scanned ? "BACKEND DATA" : "NOT RUN"}
                  </span>
                </div>
                {!summary.data.discovery.scanned ? (
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name="pulse" size={21} /></span>
                    <strong>No LAN scan recorded</strong>
                    <span>Start discovery from the LAN Discovery page to populate coverage.</span>
                  </div>
                ) : (
                  <div className="dashboard-fact-list">
                    <div><span>Last scan</span><strong>{formatTime(summary.data.discovery.last_scan_at)}</strong></div>
                    <div><span>Status</span><strong>{summary.data.discovery.scan_status ?? "unknown"}</strong></div>
                    <div>
                      <span>Addresses probed</span>
                      <strong>
                        {number(summary.data.discovery.coverage?.hosts_probed)} / {number(summary.data.discovery.coverage?.hosts_in_subnet)}
                      </strong>
                    </div>
                    <div>
                      <span>Not probed</span>
                      <strong>{number(summary.data.discovery.coverage?.unprobed_hosts)}</strong>
                    </div>
                  </div>
                )}
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div>
                    <div className="panel-kicker">DNS PROTECTION</div>
                    <h2>Provider and enforcement</h2>
                  </div>
                  <span className={`read-only-tag${summary.data.provider.configured ? "" : " unavailable"}`}>
                    {summary.data.provider.configured ? "PROVIDER CONFIGURED" : "UNCONFIGURED"}
                  </span>
                </div>
                <div className="dashboard-fact-list">
                  <div><span>Provider state</span><strong>{summary.data.provider.state}</strong></div>
                  <div><span>Provider</span><strong>{summary.data.provider.provider ?? "none"}</strong></div>
                  <div>
                    <span>Provider filtering ready</span>
                    <strong>{summary.data.enforcement.provider_ready ? "Yes" : "No"}</strong>
                  </div>
                  <div>
                    <span>Router-wide protection</span>
                    <strong className="warning-text">Not verified</strong>
                  </div>
                </div>
                <p className="panel-footer-note">
                  Provider-level filtering does not prove router DHCP/DNS or client-level enforcement.
                </p>
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div>
                    <div className="panel-kicker">BANDWIDTH</div>
                    <h2>Host interface traffic</h2>
                  </div>
                  <span className="read-only-tag">LOCAL HOST</span>
                </div>
                {!summary.data.bandwidth.available || !summary.data.bandwidth.interface ? (
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name="alert" size={21} /></span>
                    <strong>Interface counters unavailable</strong>
                    <span>The backend could not read local interface counters.</span>
                  </div>
                ) : (
                  <div className="dashboard-fact-list">
                    <div><span>Interface</span><strong data-no-translate="true">{summary.data.bandwidth.interface}</strong></div>
                    <div><span>Download now</span><strong>{rate(summary.data.bandwidth.rx_bytes_per_second)}</strong></div>
                    <div><span>Upload now</span><strong>{rate(summary.data.bandwidth.tx_bytes_per_second)}</strong></div>
                    <div><span>Samples collected</span><strong>{number(summary.data.bandwidth.sample_count)}</strong></div>
                  </div>
                )}
                <p className="panel-footer-note">{summary.data.bandwidth.scope}</p>
              </article>
            </section>
          </>
        )}
      </section>
    </LocalizedTree>
  );
}
