import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getBandwidthHistory,
  getBandwidthInterfaces,
  getBandwidthStatus,
  sampleBandwidth,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import type {
  ApiError,
  BandwidthInterface,
  BandwidthSample,
  BandwidthStatus,
} from "../types";

function toApiError(error: unknown): ApiError {
  return error instanceof Error ? error : new Error(String(error));
}

function bytes(value: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function rate(value: number | undefined) {
  return typeof value === "number" ? `${bytes(value)}/s` : "—";
}

export function BandwidthMonitorPage() {
  const [interfaces, setInterfaces] = useState<BandwidthInterface[]>([]);
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState<BandwidthStatus | null>(null);
  const [samples, setSamples] = useState<BandwidthSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [sampling, setSampling] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async (interfaceName?: string) => {
    setLoading(true);
    setError(null);
    try {
      const list = await getBandwidthInterfaces();
      setInterfaces(list);
      const active = interfaceName || selected || list.find((item) => item.active)?.name || list[0]?.name;
      if (!active) {
        setStatus(null);
        setSamples([]);
        return;
      }
      setSelected(active);
      const [statusResult, historyResult] = await Promise.all([
        getBandwidthStatus(active),
        getBandwidthHistory(active, 60),
      ]);
      setStatus(statusResult);
      setSamples(historyResult.samples);
    } catch (loadError) {
      setError(toApiError(loadError));
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    void load();
    // Load once on mount; subsequent loads are explicit or interface-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const takeSample = async () => {
    if (!selected) return;
    setSampling(true);
    setMessage("");
    setError(null);
    try {
      const result = await sampleBandwidth(selected, 1000);
      setMessage(
        `Measured ${result.interface} over ${result.interval_seconds}s: ↓ ${rate(result.rx_bytes_per_second)}, ↑ ${rate(result.tx_bytes_per_second)}.`,
      );
      const [statusResult, historyResult] = await Promise.all([
        getBandwidthStatus(selected),
        getBandwidthHistory(selected, 60),
      ]);
      setStatus(statusResult);
      setSamples(historyResult.samples);
    } catch (sampleError) {
      setError(toApiError(sampleError));
    } finally {
      setSampling(false);
    }
  };

  const maxRate = useMemo(
    () => Math.max(1, ...samples.flatMap((item) => [item.rx_bytes_per_second, item.tx_bytes_per_second])),
    [samples],
  );

  return (
    <LocalizedTree>
      <section className="bandwidth-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> HOST TELEMETRY</div>
            <h1>Bandwidth <span>monitor.</span></h1>
            <p className="page-description">
              Traffic measured by Netra on this host interface. This is not router-wide or per-client bandwidth monitoring.
            </p>
          </div>
          <button className="refresh-button" type="button" onClick={() => void load(selected)} disabled={loading}>
            <Icon name="refresh" size={16} />
            <span>{loading ? "Refreshing…" : "Refresh"}</span>
          </button>
        </div>

        <div className="bandwidth-scope-note">
          <Icon name="lock" size={16} />
          <span>
            Read-only kernel counters from <code>/proc/net/dev</code>. No packet capture, root access or router changes are used.
          </span>
        </div>

        {error && <div className="panel-state error-state"><ErrorMessage error={error} /></div>}
        {loading && <div className="panel-state"><LoadingValue /><span>Reading interface counters…</span></div>}

        {!loading && interfaces.length === 0 && !error && (
          <div className="empty-state">
            <span className="empty-icon"><Icon name="alert" size={21} /></span>
            <strong>No interface counters available</strong>
            <span>The backend could not read <code>/proc/net/dev</code> on this host.</span>
          </div>
        )}

        {!loading && interfaces.length > 0 && (
          <>
            <section className="panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">SAMPLER CONTROL</div>
                  <h2>Local interface</h2>
                </div>
                <span className="read-only-tag">
                  {status?.monitoring ? `${status.sample_count} SAMPLES` : "NO SAMPLES"}
                </span>
              </div>
              <div className="bandwidth-controls">
                <label className="filter-control">
                  <span>Interface</span>
                  <select
                    value={selected}
                    onChange={(event) => {
                      setSelected(event.target.value);
                      void load(event.target.value);
                    }}
                  >
                    {interfaces.map((item) => (
                      <option key={item.name} value={item.name}>
                        {item.name}{item.active ? " (active route)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="primary-button" type="button" onClick={() => void takeSample()} disabled={sampling}>
                  {sampling ? "Sampling for 1s…" : "Take 1-second sample"}
                </button>
                {message && <span role="status">{message}</span>}
              </div>
              {status && (
                <div className="dashboard-fact-list">
                  <div><span>Active route interface</span><strong data-no-translate="true">{status.active_interface ?? "unknown"}</strong></div>
                  <div><span>Sampling interval</span><strong>{status.sampling_interval_ms} ms</strong></div>
                  <div><span>History retention</span><strong>{status.retention_samples} samples</strong></div>
                  <div><span>Monitoring status</span><strong>{status.monitoring ? "Sampling active" : "Ready; no sample yet"}</strong></div>
                </div>
              )}
            </section>

            {status && (
              <section className="metric-grid">
                <article className="metric-card">
                  <div className="metric-top"><span className="metric-label">DOWNLOAD NOW</span><span className="metric-icon blue"><Icon name="arrow" size={16} /></span></div>
                  <div className="metric-value">{rate(status.latest?.rx_bytes_per_second)}</div>
                </article>
                <article className="metric-card">
                  <div className="metric-top"><span className="metric-label">UPLOAD NOW</span><span className="metric-icon violet"><Icon name="arrow" size={16} /></span></div>
                  <div className="metric-value">{rate(status.latest?.tx_bytes_per_second)}</div>
                </article>
                <article className="metric-card">
                  <div className="metric-top"><span className="metric-label">TOTAL RECEIVED</span><span className="metric-icon green"><Icon name="pulse" size={16} /></span></div>
                  <div className="metric-value">{bytes(status.cumulative.rx_bytes)}</div>
                </article>
                <article className="metric-card">
                  <div className="metric-top"><span className="metric-label">TOTAL SENT</span><span className="metric-icon amber"><Icon name="pulse" size={16} /></span></div>
                  <div className="metric-value">{bytes(status.cumulative.tx_bytes)}</div>
                </article>
              </section>
            )}

            <section className="panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">SAMPLED HISTORY</div>
                  <h2>Throughput</h2>
                </div>
                <span className="read-only-tag">{samples.length} RETURNED</span>
              </div>
              {samples.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon"><Icon name="pulse" size={21} /></span>
                  <strong>No samples collected</strong>
                  <span>Take a sample to populate the local throughput chart.</span>
                </div>
              ) : (
                <div className="bandwidth-chart">
                  {samples.map((sample) => (
                    <div className="bandwidth-chart-row" key={`${sample.sampled_at}-${sample.rx_bytes_delta}`}>
                      <span className="bandwidth-chart-label">
                        {new Date(sample.sampled_at).toLocaleTimeString()}
                      </span>
                      <div className="bandwidth-chart-track">
                        <span
                          className="bandwidth-chart-bar rx"
                          style={{ width: `${(sample.rx_bytes_per_second / maxRate) * 100}%` }}
                          title={`Download ${rate(sample.rx_bytes_per_second)}`}
                        />
                        <span
                          className="bandwidth-chart-bar tx"
                          style={{ width: `${(sample.tx_bytes_per_second / maxRate) * 100}%` }}
                          title={`Upload ${rate(sample.tx_bytes_per_second)}`}
                        />
                      </div>
                      <span className="bandwidth-chart-value">
                        ↓ {rate(sample.rx_bytes_per_second)} · ↑ {rate(sample.tx_bytes_per_second)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <p className="panel-footer-note">
                Cumulative totals come from kernel counters and may include traffic before Netra started.
              </p>
            </section>
          </>
        )}
      </section>
    </LocalizedTree>
  );
}
