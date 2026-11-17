import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiRequestError,
  getEnforcementStatus,
  getPolicies,
  getPolicyApprovalStatus,
  getPolicyExecutionStatus,
  getPolicyRollbackStatus,
  getPolicyVerificationStatus,
  getRecoveryStatus,
  getSnapshot,
  getSnapshots,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import type {
  ApiError,
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
    <section className="panel enforcement-policy-panel">
      <div className="panel-header enforcement-policy-header">
        <div>
          <div className="panel-kicker">SELECTED POLICY · #{policy.id}</div>
          <h2>{policyLabel}</h2>
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
                This is a status flag only. The snapshot rollback endpoint is not implemented and no rollback action is available here.
              </p>
            </>
          )}
        </PolicyStatusCard>
      </div>
    </section>
  );
}

export function EnforcementRecoveryPage() {
  const [enforcement, setEnforcement] = useState<ResourceState<EnforcementStatus>>({
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
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setEnforcement({ status: "loading" });
    setRecovery({ status: "loading" });
    setSnapshots({ status: "loading" });
    setPolicies({ status: "loading" });

    void Promise.allSettled([
      getEnforcementStatus(),
      getRecoveryStatus(),
      getSnapshots(),
      getPolicies(),
    ]).then(([enforcementResult, recoveryResult, snapshotsResult, policiesResult]) => {
      if (!active) {
        return;
      }
      setEnforcement(
        enforcementResult.status === "fulfilled"
          ? { status: "ready", data: enforcementResult.value }
          : { status: "error", error: toApiError(enforcementResult.reason) },
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

  return (
    <section className="enforcement-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> OPERATIONS STATUS</div>
          <h1>Enforcement <span>&amp; recovery.</span></h1>
          <p className="page-description">
            Inspect backend-reported policy, verification, snapshot, and recovery state.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => setReloadVersion((version) => version + 1)}
          disabled={
            enforcement.status === "loading" ||
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
          Status responses do not prove that DNS traffic is being filtered. This page performs read-only status and snapshot reads; it does not approve, apply, enforce, create snapshots, or attempt recovery.
        </span>
      </div>

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
                  ? "The API reports a configured backend only. Its adapter does not implement policy application; traffic protection is not confirmed."
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

      <div className="enforcement-limitation">
        The backend's policy apply path returns failure even when a backend is configured. Snapshot rollback returns “not_implemented” for configured backends, and verification currently reports “not_verified”. Recovery status is a fixed report, not a recovery operation. No enforcement, restoration, or active protection is claimed by this page.
      </div>
    </section>
  );
}
