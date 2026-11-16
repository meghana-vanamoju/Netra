import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  getAudit,
  getAuditFindings,
  getAuditReports,
  getDevices,
  runAudit,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import type {
  ApiError,
  AuditDetail,
  AuditFinding,
  AuditReport,
  AuditRunResponse,
  Device,
  ResourceState,
} from "../types";

type AuditScope = "network" | "device";

const severityOrder = ["critical", "high", "medium", "low", "informational"];

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function scopeLabel(scope: string) {
  if (scope === "network") {
    return "Network";
  }
  if (scope === "device") {
    return "Device";
  }
  return `Unknown scope: ${scope || "not provided"}`;
}

function deviceLabel(deviceId: number | null, devicesById: Map<number, Device>) {
  if (deviceId === null) {
    return "No device linked";
  }
  const device = devicesById.get(deviceId);
  const identity = device?.hostname || device?.ip_address;
  return identity
    ? `${identity} · Device #${deviceId}`
    : `Device #${deviceId} · identity unavailable`;
}

function severityClass(severity: string) {
  const normalized = severity.toLocaleLowerCase();
  return severityOrder.includes(normalized) ? normalized : "unknown";
}

function FindingsList({
  findings,
  devicesById,
}: {
  findings: AuditFinding[];
  devicesById: Map<number, Device>;
}) {
  if (findings.length === 0) {
    return (
      <div className="audit-empty-state">
        <span className="empty-icon"><Icon name="check" size={19} /></span>
        <strong>No findings reported</strong>
        <span>This completed audit returned an empty findings list.</span>
      </div>
    );
  }

  const grouped = new Map<string, AuditFinding[]>();
  for (const finding of findings) {
    const key = finding.severity || "Unknown";
    grouped.set(key, [...(grouped.get(key) ?? []), finding]);
  }
  const severityKeys = [...grouped.keys()].sort((left, right) => {
    const leftIndex = severityOrder.indexOf(left.toLocaleLowerCase());
    const rightIndex = severityOrder.indexOf(right.toLocaleLowerCase());
    return (leftIndex < 0 ? severityOrder.length : leftIndex) -
      (rightIndex < 0 ? severityOrder.length : rightIndex) ||
      left.localeCompare(right);
  });

  return (
    <div className="audit-findings-list">
      {severityKeys.map((severity) => (
        <section className="audit-severity-group" key={severity}>
          <div className="audit-severity-heading">
            <span className={`audit-severity-dot ${severityClass(severity)}`} />
            <h3>{severity}</h3>
            <span>{grouped.get(severity)?.length ?? 0}</span>
          </div>
          {grouped.get(severity)?.map((finding) => (
            <details className="audit-finding" key={finding.id}>
              <summary>
                <span className={`audit-severity-tag ${severityClass(finding.severity)}`}>
                  {finding.severity || "Unknown"}
                </span>
                <span className="audit-finding-title">{finding.title || "Untitled finding"}</span>
                <span className="audit-rule-tag">{finding.detection_rule || "Rule not provided"}</span>
              </summary>
              <div className="audit-finding-body">
                <p>{finding.description || "Description not provided by the audit result."}</p>
                <dl className="audit-finding-meta">
                  <div>
                    <dt>Device</dt>
                    <dd>{deviceLabel(finding.device_id, devicesById)}</dd>
                  </div>
                  <div>
                    <dt>Finding timestamp</dt>
                    <dd>{finding.timestamp ? formatDate(finding.timestamp) : "Not provided"}</dd>
                  </div>
                  <div>
                    <dt>Detection rule</dt>
                    <dd>{finding.detection_rule || "Not provided"}</dd>
                  </div>
                </dl>
                <div className="audit-evidence">
                  <h4>Evidence</h4>
                  {finding.evidence?.length ? (
                    <ul>
                      {finding.evidence.map((item, index) => <li key={`${finding.id}-evidence-${index}`}>{item}</li>)}
                    </ul>
                  ) : (
                    <p className="audit-unknown-evidence">No evidence details were included in this finding.</p>
                  )}
                </div>
                <div className="audit-next-step">
                  <h4>Recommended next step</h4>
                  <p>{finding.recommended_next_step || "Not provided by the audit result."}</p>
                </div>
              </div>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

export function PrivacyAuditPage() {
  const [history, setHistory] = useState<ResourceState<AuditReport[]>>({
    status: "loading",
  });
  const [devices, setDevices] = useState<ResourceState<Device[]>>({
    status: "loading",
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ResourceState<AuditDetail>>({
    status: "loading",
  });
  const [findings, setFindings] = useState<ResourceState<AuditFinding[]>>({
    status: "loading",
  });
  const [scope, setScope] = useState<AuditScope>("network");
  const [deviceId, setDeviceId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [runError, setRunError] = useState<ApiError | null>(null);
  const [runResult, setRunResult] = useState<AuditRunResponse | null>(null);
  const [historyReload, setHistoryReload] = useState(0);

  const reloadHistory = useCallback(() => {
    setHistory({ status: "loading" });
    void getAuditReports().then(
      (reports) => setHistory({ status: "ready", data: reports }),
      (error: unknown) => setHistory({ status: "error", error: toApiError(error) }),
    );
  }, []);

  useEffect(() => {
    reloadHistory();
    void getDevices().then(
      (items) => setDevices({ status: "ready", data: items }),
      (error: unknown) => setDevices({ status: "error", error: toApiError(error) }),
    );
  }, [historyReload, reloadHistory]);

  useEffect(() => {
    if (history.status === "ready" && selectedId === null && history.data.length > 0) {
      setSelectedId(history.data[0].id);
    }
  }, [history, selectedId]);

  useEffect(() => {
    if (selectedId === null) {
      setDetail({ status: "loading" });
      setFindings({ status: "loading" });
      return;
    }
    let active = true;
    setDetail({ status: "loading" });
    setFindings({ status: "loading" });

    void Promise.allSettled([getAudit(selectedId), getAuditFindings(selectedId)]).then(
      ([detailResult, findingsResult]) => {
        if (!active) {
          return;
        }
        setDetail(
          detailResult.status === "fulfilled"
            ? { status: "ready", data: detailResult.value }
            : { status: "error", error: toApiError(detailResult.reason) },
        );
        setFindings(
          findingsResult.status === "fulfilled"
            ? { status: "ready", data: findingsResult.value }
            : { status: "error", error: toApiError(findingsResult.reason) },
        );
      },
    );

    return () => {
      active = false;
    };
  }, [selectedId]);

  const devicesById = useMemo(
    () =>
      new Map(
        devices.status === "ready"
          ? devices.data.map((device) => [device.id, device])
          : [],
      ),
    [devices],
  );

  const selectedReport =
    history.status === "ready"
      ? history.data.find((report) => report.id === selectedId)
      : undefined;
  const selectedRun = runResult && runResult.audit_id === selectedId ? runResult : null;

  const submitAudit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRunError(null);
    setRunResult(null);

    if (scope === "device" && !deviceId) {
      setRunError(new Error("Select an inventory device before starting a device audit."));
      return;
    }

    setSubmitting(true);
    try {
      const result = await runAudit(
        scope,
        scope === "device" ? Number(deviceId) : undefined,
      );
      setRunResult(result);
      setSelectedId(result.audit_id);
      setHistoryReload((version) => version + 1);
    } catch (error) {
      setRunError(toApiError(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="audit-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> PRIVACY &amp; SECURITY</div>
          <h1>Privacy <span>audit.</span></h1>
          <p className="page-description">
            Review evidence-based reports about inventory metadata and recorded DNS activity.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => setHistoryReload((version) => version + 1)}
          disabled={history.status === "loading"}
        >
          <Icon name="refresh" size={16} />
          <span>{history.status === "loading" ? "Refreshing…" : "Refresh history"}</span>
        </button>
      </div>

      <div className="audit-safety-note">
        <Icon name="lock" size={16} />
        <span>
          Audits are read-only assessments of stored inventory and DNS records. A report is saved only after you start an audit; no policy is applied and no network scan is started.
        </span>
      </div>

      <section className="audit-capability-grid" aria-label="Audit capabilities">
        <article className="audit-capability-card">
          <span className="metric-icon blue"><Icon name="grid" size={17} /></span>
          <div>
            <strong>Network audit</strong>
            <span>Evaluates all devices currently in inventory and their recorded DNS events.</span>
          </div>
          <span className="audit-available">SUPPORTED SCOPE</span>
        </article>
        <article className="audit-capability-card">
          <span className="metric-icon violet"><Icon name="devices" size={17} /></span>
          <div>
            <strong>Device audit</strong>
            <span>Evaluates one selected inventory device and its recorded DNS events.</span>
          </div>
          <span className={`audit-available${devices.status === "error" ? " unavailable" : ""}`}>
            {devices.status === "error"
              ? "TARGET LIST UNAVAILABLE"
              : devices.status === "ready" && devices.data.length === 0
                ? "NO TARGETS"
                : "SUPPORTED SCOPE"}
          </span>
        </article>
      </section>

      <section className="panel audit-run-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">USER-INITIATED ACTION</div>
            <h2>Run an audit</h2>
          </div>
          <span className="read-only-tag"><Icon name="lock" size={12} /> READ-ONLY ASSESSMENT</span>
        </div>
        <form
          className={`audit-run-form${scope === "device" ? " is-device" : ""}`}
          onSubmit={(event) => void submitAudit(event)}
        >
          <label className="filter-control">
            <span>Audit scope</span>
            <select
              value={scope}
              onChange={(event) => {
                setScope(event.target.value as AuditScope);
                setRunError(null);
              }}
              disabled={submitting}
            >
              <option value="network">Entire network inventory</option>
              <option value="device">One device</option>
            </select>
          </label>
          {scope === "device" && (
            <div className="audit-device-control">
              <label className="filter-control">
                <span>Target device</span>
                <select
                  value={deviceId}
                  onChange={(event) => setDeviceId(event.target.value)}
                  disabled={devices.status !== "ready" || devices.data.length === 0 || submitting}
                  required
                >
                  <option value="">
                    {devices.status === "loading"
                      ? "Loading inventory…"
                      : devices.status === "error"
                        ? "Inventory unavailable"
                        : devices.data.length === 0
                          ? "No devices in inventory"
                          : "Choose a device"}
                  </option>
                  {devices.status === "ready" && devices.data.map((device) => (
                    <option value={device.id} key={device.id}>
                      {device.hostname || "Unknown hostname"} · {device.ip_address} · #{device.id}
                    </option>
                  ))}
                </select>
              </label>
              {devices.status === "error" && <ErrorMessage error={devices.error} />}
            </div>
          )}
          <button
            className="primary-button"
            type="submit"
            disabled={
              submitting ||
              (scope === "device" &&
                (devices.status !== "ready" || devices.data.length === 0 || !deviceId))
            }
          >
            <Icon name="shield" size={16} />
            <span>{submitting ? "Running audit…" : "Start audit"}</span>
          </button>
        </form>
        {runError && (
          <div className="audit-run-error" role="alert">
            <strong>Audit was not confirmed</strong>
            <ErrorMessage error={runError} />
            <span>
              Check the saved history before retrying if the connection failed while the request was in progress.
            </span>
          </div>
        )}
        {selectedRun && (
          <div className="audit-run-success" role="status">
            <span className="audit-confirmation-icon"><Icon name="check" size={17} /></span>
            <div>
              <strong>Audit completion confirmed by the backend</strong>
              <span>
                Report #{selectedRun.audit_id} · {selectedRun.summary.devices} device{selectedRun.summary.devices === 1 ? "" : "s"} assessed · {selectedRun.findings} finding{selectedRun.findings === 1 ? "" : "s"} returned
              </span>
            </div>
          </div>
        )}
      </section>

      <section className="audit-workspace">
        <aside className="panel audit-history-panel" aria-label="Audit history">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">SAVED REPORTS</div>
              <h2>Audit history</h2>
            </div>
            {history.status === "ready" && <span className="read-only-tag">{history.data.length}</span>}
          </div>
          {history.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Loading saved reports…</span></div>
          ) : history.status === "error" ? (
            <div className="audit-history-error">
              <p>Saved audit history is unavailable.</p>
              <ErrorMessage error={history.error} />
            </div>
          ) : history.data.length === 0 ? (
            <div className="audit-empty-state">
              <span className="empty-icon"><Icon name="shield" size={19} /></span>
              <strong>No saved audits</strong>
              <span>Start an audit to create the first report.</span>
            </div>
          ) : (
            <div className="audit-history-list">
              {history.data.map((report) => (
                <button
                  type="button"
                  className={`audit-history-item${report.id === selectedId ? " selected" : ""}`}
                  key={report.id}
                  onClick={() => {
                    setRunResult(null);
                    setRunError(null);
                    setSelectedId(report.id);
                  }}
                  aria-current={report.id === selectedId ? "true" : undefined}
                >
                  <span className="audit-history-icon"><Icon name="shield" size={16} /></span>
                  <span className="audit-history-copy">
                    <strong>{scopeLabel(report.scope)} audit · #{report.id}</strong>
                    <span>{formatDate(report.created_at)}</span>
                  </span>
                  <span className="audit-status completed">COMPLETED</span>
                </button>
              ))}
            </div>
          )}
          <p className="audit-history-footnote">
            The backend stores completed reports only. Failed or interrupted requests are not represented in this history.
          </p>
        </aside>

        <section className="panel audit-report-panel" aria-label="Selected audit report">
          {selectedId === null ? (
            history.status === "ready" && history.data.length === 0 ? (
              <div className="audit-report-placeholder">
                <span className="empty-icon"><Icon name="shield" size={20} /></span>
                <strong>No report selected</strong>
                <span>Run an audit or select a saved report to view its results.</span>
              </div>
            ) : history.status === "error" ? (
              <div className="audit-report-placeholder">
                <span className="empty-icon"><Icon name="alert" size={20} /></span>
                <strong>Reports could not be loaded</strong>
                <span>Report details are unavailable until the backend can return the history list.</span>
              </div>
            ) : (
              <div className="panel-state"><LoadingValue /><span>Loading report…</span></div>
            )
          ) : (
            <>
              <div className="panel-header audit-report-heading">
                <div>
                  <div className="panel-kicker">AUDIT REPORT · #{selectedId}</div>
                  <h2>{selectedReport ? `${scopeLabel(selectedReport.scope)} audit results` : "Audit report"}</h2>
                </div>
                <span className={`audit-status${detail.status === "error" || findings.status === "error" ? " incomplete" : " completed"}`}>
                  {detail.status === "loading" || findings.status === "loading"
                    ? "LOADING"
                    : detail.status === "error" || findings.status === "error"
                      ? "INCOMPLETE"
                      : "COMPLETED"}
                </span>
              </div>
              {selectedReport && (
                <div className="audit-report-meta">
                  <span>{formatDate(selectedReport.created_at)}</span>
                  <span>{scopeLabel(selectedReport.scope)} scope</span>
                </div>
              )}
              {detail.status === "loading" || findings.status === "loading" ? (
                <div className="panel-state"><LoadingValue /><span>Loading report details…</span></div>
              ) : detail.status === "error" ? (
                <div className="audit-incomplete-state">
                  <strong>Report details are unavailable</strong>
                  <ErrorMessage error={detail.error} />
                  <span>The saved history entry exists, but the backend did not return its report summary.</span>
                </div>
              ) : (
                <>
                  {selectedRun && (
                    <div className="audit-report-summary-grid">
                      <div><span>DEVICES ASSESSED</span><strong>{selectedRun.summary.devices}</strong></div>
                      <div><span>FINDINGS RETURNED</span><strong>{selectedRun.findings}</strong></div>
                    </div>
                  )}
                  {!selectedRun && (
                    <div className="audit-report-summary-grid">
                      <div>
                        <span>DEVICES ASSESSED</span>
                        <strong>{typeof detail.data.summary?.devices === "number" ? detail.data.summary.devices : "Unknown"}</strong>
                      </div>
                      <div>
                        <span>FINDINGS IN SUMMARY</span>
                        <strong>{typeof detail.data.summary?.findings === "number" ? detail.data.summary.findings : detail.data.findings_count}</strong>
                      </div>
                    </div>
                  )}
                  {findings.status === "error" ? (
                    <div className="audit-incomplete-state">
                      <strong>Finding details are unavailable</strong>
                      <ErrorMessage error={findings.error} />
                      <span>The summary was returned, but individual evidence could not be loaded.</span>
                    </div>
                  ) : (
                    <>
                      <div className="audit-findings-title">
                        <div>
                          <div className="panel-kicker">RESULT DETAILS</div>
                          <h3>Findings</h3>
                        </div>
                        <span>{findings.data.length} returned</span>
                      </div>
                      <FindingsList findings={findings.data} devicesById={devicesById} />
                    </>
                  )}
                </>
              )}
            </>
          )}
        </section>
      </section>

      <p className="audit-limitations">
        The API reports findings, not a compromise verdict or risk score. An empty result means no findings were returned by this audit run; it is not a guarantee of safety. Historical audit metadata does not include the target device ID or failed-run records.
      </p>
    </section>
  );
}
