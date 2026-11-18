import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiRequestError,
  applyPolicy,
  getEnforcementReadiness,
  getEnforcementStatus,
  getPolicies,
  getPolicyApprovalStatus,
  getPolicyExecutionStatus,
  getPolicyRollbackStatus,
  getPolicyVerificationStatus,
  getRecoveryStatus,
  getSnapshot,
  getSnapshots,
  rollbackSnapshot,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import { useNetworkContext } from "../NetworkContext";
import type {
  ApiError,
  EnforcementReadiness,
  EnforcementStatus,
  PolicyApprovalStatus,
  PolicyExecutionStatus,
  PolicyRollbackStatus,
  PolicySummary,
  PolicyVerificationStatus,
  RecoveryStatus,
  ResourceState,
  SnapshotDetail,
  SnapshotSummary,
} from "../types";

type PolicyStatusData = {
  approval: ResourceState<PolicyApprovalStatus>;
  execution: ResourceState<PolicyExecutionStatus | null>;
  rollback: ResourceState<PolicyRollbackStatus>;
  verification: ResourceState<PolicyVerificationStatus>;
};

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function displayStatus(value: string) {
  return value.trim().replace(/_/g, " ");
}

function statusClass(value: string) {
  switch (value.toLocaleLowerCase()) {
    case "verified":
    case "approved":
    case "applied":
    case "ready":
      return "enforcement-status-positive";
    case "pending":
    case "applying":
    case "proposed":
    case "recommended":
      return "enforcement-status-pending";
    case "not_verified":
    case "not_implemented":
    case "unavailable":
    case "failed":
    case "reverted":
      return "enforcement-status-muted";
    default:
      return "enforcement-status-unknown";
  }
}

function PolicyStatusCard({
  title,
  state,
  emptyLabel,
  children,
}: {
  title: string;
  state: ResourceState<unknown>;
  emptyLabel?: string;
  children: ReactNode;
}) {
  return (
    <LocalizedTree>
    <article className="panel enforcement-status-card">
      <div className="panel-header">
        <h3>{title}</h3>
        {state.status === "ready" && emptyLabel && (
          <span className="enforcement-status enforcement-status-muted">
            {emptyLabel}
          </span>
        )}
      </div>
      {state.status === "loading" ? (
        <div className="panel-state"><LoadingValue /><span>Loading status…</span></div>
      ) : state.status === "error" ? (
        <ErrorMessage error={state.error} />
      ) : (
        children
      )}
    </article>
    </LocalizedTree>
  );
}

function PolicyStatusDetails({
  policy,
  value,
}: {
  policy: PolicySummary;
  value: PolicyStatusData;
}) {
  const policyLabel = policy.name || `Policy #${policy.id}`;

  return (
    <LocalizedTree>
    <section className="panel enforcement-policy-panel">
      <div className="panel-header enforcement-policy-header">
        <div>
          <div className="panel-kicker">SELECTED POLICY · #{policy.id}</div>
          <h2>
            {policy.name
              ? <span data-no-translate="true">{policy.name}</span>
              : policyLabel}
          </h2>
        </div>
        <span className="policy-status policy-status-unknown">
          {policy.status || "Status unknown"}
        </span>
      </div>

      <div className="enforcement-status-grid">
        <PolicyStatusCard
          title="Consent / approval"
          state={value.approval}
        >
          {value.approval.status === "ready" && (
            <dl className="enforcement-data-list">
              <div>
                <dt>Backend policy status</dt>
                <dd>
                  <span className={`enforcement-status ${statusClass(value.approval.data.status)}`}>
                    {displayStatus(value.approval.data.status || "unknown")}
                  </span>
                </dd>
              </div>
              <div><dt>Approver</dt><dd>{value.approval.data.approver || "Not recorded"}</dd></div>
              <div>
                <dt>Approved at</dt>
                <dd>{value.approval.data.approved_at ? formatDate(value.approval.data.approved_at) : "Not recorded"}</dd>
              </div>
              <div><dt>Linked dry-run plan</dt><dd>{value.approval.data.plan_id === null ? "Not recorded" : `Plan #${value.approval.data.plan_id}`}</dd></div>
            </dl>
          )}
        </PolicyStatusCard>

        <PolicyStatusCard
          title="Execution status"
          state={value.execution}
          emptyLabel={value.execution.status === "ready" && value.execution.data === null ? "NO EXECUTION RECORD" : undefined}
        >
          {value.execution.status === "ready" && (
            value.execution.data === null ? (
              <p className="enforcement-explanation">
                The backend reports no execution record for this policy. No execution result is available.
              </p>
            ) : (
              <>
                <p className="enforcement-status-line">
                  <span className={`enforcement-status ${statusClass(value.execution.data.status)}`}>
                    {displayStatus(value.execution.data.status || "unknown")}
                  </span>
                </p>
                <div className="enforcement-json">
                  <span>Backend execution details</span>
                  <pre>{JSON.stringify(value.execution.data.details, null, 2)}</pre>
                </div>
              </>
            )
          )}
        </PolicyStatusCard>

        <PolicyStatusCard
          title="Verification"
          state={value.verification}
        >
          {value.verification.status === "ready" && (
            <>
              <p className="enforcement-status-line">
                <span className={`enforcement-status ${statusClass(value.verification.data.status)}`}>
                  {displayStatus(value.verification.data.status || "unknown")}
                </span>
              </p>
              <p className="enforcement-explanation">
                {value.verification.data.reason || "No verification explanation was returned."}
              </p>
              {value.verification.data.status === "verified" && (
                <p className="enforcement-explanation">
                  The API reports verification for this policy; this status alone does not confirm traffic-level protection.
                </p>
              )}
            </>
          )}
        </PolicyStatusCard>

        <PolicyStatusCard
          title="Rollback status"
          state={value.rollback}
        >
          {value.rollback.status === "ready" && (
            <>
              <dl className="enforcement-data-list">
                <div><dt>Backend policy status</dt><dd>{displayStatus(value.rollback.data.status || "unknown")}</dd></div>
                <div><dt>Backend rollback-ready flag</dt><dd>{value.rollback.data.rollback_ready ? "Yes" : "No"}</dd></div>
              </dl>
              <p className="enforcement-explanation">
                This status flag is separate from the controlled rollback action below, which requires a valid snapshot and explicit confirmation.
              </p>
            </>
          )}
        </PolicyStatusCard>
      </div>
    </section>
    </LocalizedTree>
  );
}

export function EnforcementRecoveryPage() {
  const { selectedSubnet, selectedDeviceId, clearNetworkContext } = useNetworkContext();
  const [enforcement, setEnforcement] = useState<ResourceState<EnforcementStatus>>({
    status: "loading",
  });
  const [readiness, setReadiness] = useState<ResourceState<EnforcementReadiness>>({
    status: "loading",
  });
  const [recovery, setRecovery] = useState<ResourceState<RecoveryStatus>>({
    status: "loading",
  });
  const [snapshots, setSnapshots] = useState<ResourceState<SnapshotSummary[]>>({
    status: "loading",
  });
  const [policies, setPolicies] = useState<ResourceState<PolicySummary[]>>({
    status: "loading",
  });
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshot, setSnapshot] = useState<ResourceState<SnapshotDetail>>({
    status: "loading",
  });
  const [policyId, setPolicyId] = useState("");
  const [policyStatus, setPolicyStatus] = useState<PolicyStatusData | null>(null);
  const [applyConfirm, setApplyConfirm] = useState(false);
  const [applyResult, setApplyResult] = useState<Record<string, unknown> | null>(null);
  const [applyError, setApplyError] = useState<ApiError | null>(null);
  const [applying, setApplying] = useState(false);
  const [rollbackConfirm, setRollbackConfirm] = useState(false);
  const [rollbackResult, setRollbackResult] = useState<Record<string, unknown> | null>(null);
  const [rollbackError, setRollbackError] = useState<ApiError | null>(null);
  const [rollingBack, setRollingBack] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setEnforcement({ status: "loading" });
    setReadiness({ status: "loading" });
    setRecovery({ status: "loading" });
    setSnapshots({ status: "loading" });
    setPolicies({ status: "loading" });

    void Promise.allSettled([
      getEnforcementStatus(),
      getEnforcementReadiness(),
      getRecoveryStatus(),
      getSnapshots(),
      getPolicies(),
    ]).then(([enforcementResult, readinessResult, recoveryResult, snapshotsResult, policiesResult]) => {
      if (!active) {
        return;
      }
      setEnforcement(
        enforcementResult.status === "fulfilled"
          ? { status: "ready", data: enforcementResult.value }
          : { status: "error", error: toApiError(enforcementResult.reason) },
      );
      setReadiness(
        readinessResult.status === "fulfilled"
          ? { status: "ready", data: readinessResult.value }
          : { status: "error", error: toApiError(readinessResult.reason) },
      );
      setRecovery(
        recoveryResult.status === "fulfilled"
          ? { status: "ready", data: recoveryResult.value }
          : { status: "error", error: toApiError(recoveryResult.reason) },
      );
      if (snapshotsResult.status === "fulfilled") {
        setSnapshots({ status: "ready", data: snapshotsResult.value });
        setSnapshotId((current) =>
          current && snapshotsResult.value.some((item) => item.id === Number(current))
            ? current
            : "",
        );
      } else {
        setSnapshots({ status: "error", error: toApiError(snapshotsResult.reason) });
        setSnapshotId("");
      }
      if (policiesResult.status === "fulfilled") {
        setPolicies({ status: "ready", data: policiesResult.value });
        setPolicyId((current) =>
          current && policiesResult.value.some((item) => item.id === Number(current))
            ? current
            : policiesResult.value.length > 0
              ? String(policiesResult.value[0].id)
              : "",
        );
      } else {
        setPolicies({ status: "error", error: toApiError(policiesResult.reason) });
        setPolicyId("");
      }
    });

    return () => {
      active = false;
    };
  }, [reloadVersion]);

  useEffect(() => {
    if (!snapshotId) {
      setSnapshot({ status: "loading" });
      return;
    }
    let active = true;
    setSnapshot({ status: "loading" });
    void getSnapshot(Number(snapshotId)).then(
      (data) => {
        if (active) {
          setSnapshot({ status: "ready", data });
        }
      },
      (error: unknown) => {
        if (active) {
          setSnapshot({ status: "error", error: toApiError(error) });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [snapshotId]);

  useEffect(() => {
    if (!policyId) {
      setPolicyStatus(null);
      return;
    }
    let active = true;
    const policyNumber = Number(policyId);
    setPolicyStatus({
      approval: { status: "loading" },
      execution: { status: "loading" },
      rollback: { status: "loading" },
      verification: { status: "loading" },
    });

    void Promise.allSettled([
      getPolicyApprovalStatus(policyNumber),
      getPolicyExecutionStatus(policyNumber),
      getPolicyRollbackStatus(policyNumber),
      getPolicyVerificationStatus(policyNumber),
    ]).then(([approval, execution, rollback, verification]) => {
      if (!active) {
        return;
      }
      setPolicyStatus({
        approval:
          approval.status === "fulfilled"
            ? { status: "ready", data: approval.value }
            : { status: "error", error: toApiError(approval.reason) },
        execution:
          execution.status === "fulfilled"
            ? { status: "ready", data: execution.value }
            : execution.status === "rejected" && execution.reason instanceof ApiRequestError && execution.reason.status === 404
              ? { status: "ready", data: null }
              : { status: "error", error: toApiError(execution.reason) },
        rollback:
          rollback.status === "fulfilled"
            ? { status: "ready", data: rollback.value }
            : { status: "error", error: toApiError(rollback.reason) },
        verification:
          verification.status === "fulfilled"
            ? { status: "ready", data: verification.value }
            : { status: "error", error: toApiError(verification.reason) },
      });
    });

    return () => {
      active = false;
    };
  }, [policyId, reloadVersion]);

  const selectedPolicy = useMemo(
    () =>
      policies.status === "ready"
        ? policies.data.find((item) => item.id === Number(policyId))
        : undefined,
    [policies, policyId],
  );
  const selectedSnapshot = useMemo(
    () =>
      snapshots.status === "ready"
        ? snapshots.data.find((item) => item.id === Number(snapshotId))
        : undefined,
    [snapshotId, snapshots],
  );

  const handleApply = async () => {
    if (!policyId || !applyConfirm) {
      return;
    }
    setApplying(true);
    setApplyError(null);
    setApplyResult(null);
    try {
      const result = await applyPolicy(Number(policyId));
      setApplyResult(result);
      setReloadVersion((version) => version + 1);
    } catch (error) {
      setApplyError(toApiError(error));
    } finally {
      setApplying(false);
    }
  };

  const handleRollback = async () => {
    if (!snapshotId || !rollbackConfirm) {
      return;
    }
    setRollingBack(true);
    setRollbackError(null);
    setRollbackResult(null);
    try {
      const result = await rollbackSnapshot(Number(snapshotId), true);
      setRollbackResult(result);
      setReloadVersion((version) => version + 1);
    } catch (error) {
      setRollbackError(toApiError(error));
    } finally {
      setRollingBack(false);
    }
  };

  return (
    <LocalizedTree>
    <section className="enforcement-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> OPERATIONS STATUS</div>
          <h1>Enforcement <span>readiness.</span></h1>
          <p className="page-description">
            Inspect gateway, permission and provider capability evidence before any consent-gated apply, verify or rollback action.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => setReloadVersion((version) => version + 1)}
          disabled={
            enforcement.status === "loading" ||
            readiness.status === "loading" ||
            recovery.status === "loading" ||
            snapshots.status === "loading" ||
            policies.status === "loading"
          }
        >
          <Icon name="refresh" size={16} />
          <span>Refresh status</span>
        </button>
      </div>

      <div className="enforcement-safety-note">
        <Icon name="alert" size={16} />
        <span>
          Status responses do not prove that DNS traffic is being filtered. Controlled apply and rollback actions below require explicit confirmation and provider verification; no action is performed automatically.
        </span>
      </div>
      {(selectedSubnet || selectedDeviceId !== null) && (
        <div className="enforcement-context-note" role="status">
          Active context: {selectedSubnet ? <span data-no-translate="true">{selectedSubnet}</span> : "all networks"}
          {selectedDeviceId !== null ? ` · device #${selectedDeviceId}` : " · all devices"}
          <button type="button" className="secondary-button" onClick={() => clearNetworkContext()}>
            Clear device selection
          </button>
        </div>
      )}

      <section className="enforcement-overview-grid" aria-label="Backend operational status">
        <article className="panel enforcement-overview-card">
          <div className="panel-header">
            <div><div className="panel-kicker">DNS BACKEND</div><h2>Enforcement capability</h2></div>
            <span className={`metric-icon ${enforcement.status === "ready" && enforcement.data.available ? "green" : "amber"}`}>
              <Icon name="router" size={17} />
            </span>
          </div>
          {enforcement.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Checking backend status…</span></div>
          ) : enforcement.status === "error" ? (
            <ErrorMessage error={enforcement.error} />
          ) : (
            <>
              <div className="enforcement-status-line">
                <span className={`enforcement-status ${enforcement.data.available ? "enforcement-status-pending" : "enforcement-status-muted"}`}>
                  {enforcement.data.available ? "CONFIGURED" : "UNAVAILABLE"}
                </span>
                <span>{enforcement.data.backend || "No backend reported"}</span>
              </div>
              <p className="enforcement-explanation">
                {enforcement.data.available
                  ? "A configured backend is available. Policy application still requires approval, dry-run, opt-in enforcement and provider verification; traffic protection is not assumed."
                  : "The API reports no configured DNS backend. No enforcement capability is available."}
              </p>
            </>
          )}
        </article>

        <article className="panel enforcement-overview-card">
          <div className="panel-header">
            <div><div className="panel-kicker">RECOVERY API</div><h2>Recovery status</h2></div>
            <span className="metric-icon blue"><Icon name="refresh" size={17} /></span>
          </div>
          {recovery.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Checking recovery status…</span></div>
          ) : recovery.status === "error" ? (
            <ErrorMessage error={recovery.error} />
          ) : (
            <>
              <div className="enforcement-status-line">
                <span className={`enforcement-status ${recovery.data.recovery_ready ? "enforcement-status-pending" : "enforcement-status-muted"}`}>
                  {recovery.data.recovery_ready ? "REPORTED READY" : "UNAVAILABLE"}
                </span>
              </div>
              <dl className="enforcement-data-list">
                <div><dt>Interrupted executions</dt><dd>{recovery.data.interrupted_executions}</dd></div>
              </dl>
              <p className="enforcement-explanation">
                These are the values returned by the recovery status endpoint; it currently returns fixed status values and exposes no recovery action.
              </p>
            </>
          )}
        </article>
      </section>

      <section className="panel enforcement-readiness-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">CAPABILITY AUDIT</div>
            <h2>Enforcement readiness</h2>
          </div>
          <span className={`read-only-tag${readiness.status === "ready" && readiness.data.provider_ready ? "" : " unavailable"}`}>
            {readiness.status === "ready"
              ? readiness.data.provider_ready
                ? "PROVIDER READY"
                : "PROVIDER NOT READY"
              : "CHECKING"}
          </span>
        </div>
        {readiness.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Checking gateway, permissions and provider modes…</span></div>
        ) : readiness.status === "error" ? (
          <ErrorMessage error={readiness.error} />
        ) : (
          <>
            <div className="enforcement-readiness-grid">
              <div className="enforcement-readiness-column">
                <h3>Local network</h3>
                <dl className="enforcement-data-list">
                  <div><dt>Interface</dt><dd data-no-translate="true">{readiness.data.local_network.interface ?? "unknown"}</dd></div>
                  <div><dt>Local IP</dt><dd data-no-translate="true">{readiness.data.local_network.ip_address ?? "unknown"}</dd></div>
                  <div><dt>Gateway</dt><dd data-no-translate="true">{readiness.data.local_network.gateway ?? "unknown"}</dd></div>
                  <div><dt>Subnet</dt><dd data-no-translate="true">{readiness.data.local_network.subnet ?? "unknown"}</dd></div>
                </dl>
                <h3>Required permissions</h3>
                <ul className="enforcement-readiness-list">
                  {readiness.data.required_permissions.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
              <div className="enforcement-readiness-column">
                <h3>Supported modes</h3>
                <ul className="enforcement-readiness-list">
                  {readiness.data.supported_modes.map((item) => (
                    <li key={item.mode}>
                      <strong>{item.mode}</strong> · {item.supported ? "supported" : "unavailable"} · {item.scope}
                    </li>
                  ))}
                </ul>
                <h3>Unsupported modes</h3>
                <ul className="enforcement-readiness-list">
                  {readiness.data.unsupported_modes.map((item) => (
                    <li key={item.mode}><strong>{item.mode}</strong> · {item.reason}</li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="enforcement-readiness-alerts">
              <p><strong>Network-wide readiness:</strong> {readiness.data.network_wide_ready ? "Ready" : "Not verified"}</p>
              <p><strong>Snapshot records:</strong> {readiness.data.snapshot_count}</p>
              {readiness.data.warnings.map((warning) => (
                <p key={warning} className="warning-text">{warning}</p>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel enforcement-policy-select-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">READ-ONLY POLICY STATUS</div>
            <h2>Consent, execution &amp; verification</h2>
          </div>
          <span className="read-only-tag">NO ACTIONS</span>
        </div>
        {policies.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Loading policies…</span></div>
        ) : policies.status === "error" ? (
          <ErrorMessage error={policies.error} />
        ) : policies.data.length === 0 ? (
          <div className="enforcement-empty-state">
            <span className="empty-icon"><Icon name="shield" size={19} /></span>
            <strong>No saved policies to inspect</strong>
            <span>Policy consent and execution status are unavailable until a policy exists.</span>
          </div>
        ) : (
          <>
            <label className="filter-control enforcement-policy-select">
              <span>Select saved policy</span>
              <select value={policyId} onChange={(event) => setPolicyId(event.target.value)}>
                {policies.data.map((policy) => (
                  <option value={policy.id} key={policy.id}>
                    {policy.name || "Unnamed policy"} · #{policy.id} · {policy.status || "Unknown status"}
                  </option>
                ))}
              </select>
            </label>
            {selectedPolicy && policyStatus ? (
              <PolicyStatusDetails policy={selectedPolicy} value={policyStatus} />
            ) : policyId ? (
              <div className="panel-state"><LoadingValue /><span>Loading policy status…</span></div>
            ) : null}
          </>
        )}
      </section>

      <section className="panel snapshot-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">SAVED CONFIGURATION RECORDS</div>
            <h2>Snapshots</h2>
          </div>
          {snapshots.status === "ready" && (
            <span className="read-only-tag">{snapshots.data.length} SAVED</span>
          )}
        </div>
        <p className="enforcement-explanation">
          A snapshot stores a backend label, opaque state object, checksum, and optional policy ID. Inspecting its integrity only checks the stored state against its checksum; it does not restore configuration.
        </p>
        {snapshots.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Loading snapshots…</span></div>
        ) : snapshots.status === "error" ? (
          <ErrorMessage error={snapshots.error} />
        ) : snapshots.data.length === 0 ? (
          <div className="enforcement-empty-state">
            <span className="empty-icon"><Icon name="lock" size={19} /></span>
            <strong>No saved snapshots</strong>
            <span>The backend returned no configuration snapshot records.</span>
          </div>
        ) : (
          <>
            <label className="filter-control enforcement-policy-select">
              <span>Inspect a saved snapshot</span>
              <select
                value={snapshotId}
                onChange={(event) => setSnapshotId(event.target.value)}
              >
                <option value="">Choose a snapshot</option>
                {snapshots.data.map((item) => (
                  <option value={item.id} key={item.id}>
                    Snapshot #{item.id} · {item.backend || "Backend unknown"} · {formatDate(item.created_at)}
                  </option>
                ))}
              </select>
            </label>
            {selectedSnapshot && (
              <div className="snapshot-summary">
                <span>Snapshot #{selectedSnapshot.id}</span>
                <span>{selectedSnapshot.backend || "Backend not recorded"}</span>
                <span>{formatDate(selectedSnapshot.created_at)}</span>
                <span>Checksum: {selectedSnapshot.checksum || "Not provided"}</span>
              </div>
            )}
            {!snapshotId ? (
              <div className="snapshot-inspection-placeholder">Select a snapshot to inspect its saved state and checksum result.</div>
            ) : snapshot.status === "loading" ? (
              <div className="panel-state"><LoadingValue /><span>Inspecting snapshot…</span></div>
            ) : snapshot.status === "error" ? (
              <ErrorMessage error={snapshot.error} />
            ) : (
              <div className="snapshot-inspection">
                <div className="panel-header">
                  <strong>Snapshot #{snapshot.data.id} state</strong>
                  <span className={`enforcement-status ${snapshot.data.integrity_ok ? "enforcement-status-positive" : "enforcement-status-muted"}`}>
                    {snapshot.data.integrity_ok ? "CHECKSUM MATCH" : "CHECKSUM MISMATCH"}
                  </span>
                </div>
                <pre>{JSON.stringify(snapshot.data.state, null, 2)}</pre>
                <p className="enforcement-explanation">
                  {snapshot.data.integrity_ok
                    ? "The backend reports that the stored state matches its saved checksum."
                    : "The backend reports a checksum mismatch. The snapshot is not considered verified."}
                  {" "}This does not indicate whether the state is currently applied.
                </p>
              </div>
            )}
          </>
        )}
      </section>

      <section className="panel enforcement-policy-select-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">CONTROLLED ACTIONS</div>
            <h2>Consent-gated apply and rollback</h2>
          </div>
          <span className="read-only-tag">EXPLICIT CONFIRMATION REQUIRED</span>
        </div>
        <p className="enforcement-explanation">
          Apply requires an approved policy with a linked dry-run plan, a configured DNS provider,
          and <code>NETRA_DNS_ENFORCEMENT_ENABLED=true</code>. Rollback requires a valid snapshot.
        </p>
        <label className="filter-control enforcement-policy-select">
          <span>Select saved policy</span>
          <select value={policyId} onChange={(event) => setPolicyId(event.target.value)}>
            <option value="">Choose a policy</option>
            {policies.status === "ready" &&
              policies.data.map((policy) => (
                <option value={policy.id} key={policy.id}>
                  {policy.name || "Unnamed policy"} · #{policy.id} · {policy.status || "Unknown status"}
                </option>
              ))}
          </select>
        </label>
        <label className="filter-control">
          <input
            type="checkbox"
            checked={applyConfirm}
            onChange={(event) => setApplyConfirm(event.target.checked)}
          />
          I confirm that this policy may change DNS filtering rules.
        </label>
        <button
          className="primary-button"
          type="button"
          disabled={!policyId || !applyConfirm || applying}
          onClick={() => void handleApply()}
        >
          {applying ? "Applying…" : "Apply selected policy"}
        </button>
        {applyError && <ErrorMessage error={applyError} />}
        {applyResult && (
          <pre className="enforcement-json">{JSON.stringify(applyResult, null, 2)}</pre>
        )}

        <label className="filter-control enforcement-policy-select">
          <span>Inspect a saved snapshot</span>
          <select
            value={snapshotId}
            onChange={(event) => setSnapshotId(event.target.value)}
          >
            <option value="">Choose a snapshot</option>
            {snapshots.status === "ready" &&
              snapshots.data.map((item) => (
                <option value={item.id} key={item.id}>
                  Snapshot #{item.id} · {item.backend || "Backend unknown"}
                </option>
              ))}
          </select>
        </label>
        <label className="filter-control">
          <input
            type="checkbox"
            checked={rollbackConfirm}
            onChange={(event) => setRollbackConfirm(event.target.checked)}
          />
          I confirm that this snapshot should be restored.
        </label>
        <button
          className="secondary-button"
          type="button"
          disabled={!snapshotId || !rollbackConfirm || rollingBack}
          onClick={() => void handleRollback()}
        >
          {rollingBack ? "Rolling back…" : "Roll back selected snapshot"}
        </button>
        {rollbackError && <ErrorMessage error={rollbackError} />}
        {rollbackResult && (
          <pre className="enforcement-json">{JSON.stringify(rollbackResult, null, 2)}</pre>
        )}
      </section>

      <div className="enforcement-limitation">
        Apply and rollback use the existing backend consent and snapshot APIs. Traffic-level
        protection is still verified through provider query-log evidence, not assumed from API success.
      </div>
    </section>
    </LocalizedTree>
  );
}
