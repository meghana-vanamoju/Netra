import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  createPolicy,
  deletePolicy,
  generatePolicyPlan,
  getAuditFindings,
  getAuditReports,
  getDevices,
  getDryRunImpact,
  getPolicies,
  getPolicy,
  getSavedDryRunPlan,
  runPolicyDryRun,
  updatePolicy,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import { useNetworkContext } from "../NetworkContext";
import type {
  ApiError,
  AuditFinding,
  AuditReport,
  Device,
  DryRunImpact,
  DryRunResult,
  PolicyDetail,
  PolicySummary,
  ResourceState,
  SavedDryRunPlan,
} from "../types";

type PolicyRow = {
  summary: PolicySummary;
  detail: ResourceState<PolicyDetail>;
};

type GeneratedPlan = {
  auditId: number;
  policyIds: number[];
};

type SavedDryRun = {
  plan: ResourceState<SavedDryRunPlan>;
  impact: ResourceState<DryRunImpact>;
};

type PolicyEditor = {
  open: boolean;
  editingId: number | null;
  name: string;
  description: string;
  targetDeviceId: number | null;
  enabled: boolean;
  blockedDomains: string;
  allowedDomains: string;
  deleteConfirmId: number | null;
  busy: boolean;
  error: ApiError | null;
  message: string;
};

const emptyEditor = (targetDeviceId: number | null): PolicyEditor => ({
  open: false,
  editingId: null,
  name: "",
  description: "",
  targetDeviceId,
  enabled: true,
  blockedDomains: "",
  allowedDomains: "",
  deleteConfirmId: null,
  busy: false,
  error: null,
  message: "",
});

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function auditScope(scope: string) {
  if (scope === "network") {
    return "Network";
  }
  if (scope === "device") {
    return "Device";
  }
  return `Unknown scope: ${scope || "not provided"}`;
}

function statusClass(status: string) {
  switch (status.toLocaleLowerCase()) {
    case "recommended":
    case "proposed":
    case "dry-run completed":
    case "awaiting approval":
      return "policy-status-pending";
    case "approved":
    case "applying":
    case "applied":
      return "policy-status-attention";
    case "failed":
    case "reverted":
      return "policy-status-inactive";
    default:
      return "policy-status-unknown";
  }
}

async function loadPolicyRows(): Promise<PolicyRow[]> {
  const policies = await getPolicies();
  const detailResults = await Promise.allSettled(
    policies.map((policy) => getPolicy(policy.id)),
  );
  return policies.map((policy, index) => {
    const result = detailResults[index];
    return {
      summary: policy,
      detail:
        result.status === "fulfilled"
          ? { status: "ready", data: result.value }
          : { status: "error", error: toApiError(result.reason) },
    };
  });
}

export function PolicyPlanningPage() {
  const { selectedSubnet, selectedDeviceId, clearNetworkContext } = useNetworkContext();
  const [audits, setAudits] = useState<ResourceState<AuditReport[]>>({
    status: "loading",
  });
  const [policies, setPolicies] = useState<ResourceState<PolicyRow[]>>({
    status: "loading",
  });
  const [selectedAuditId, setSelectedAuditId] = useState("");
  const [auditFindings, setAuditFindings] = useState<ResourceState<AuditFinding[]>>({
    status: "loading",
  });
  const [auditFindingsKey, setAuditFindingsKey] = useState<number | null>(null);
  const [selectedPolicyIds, setSelectedPolicyIds] = useState<number[]>([]);
  const [planningConfirmed, setPlanningConfirmed] = useState(false);
  const [dryRunConfirmed, setDryRunConfirmed] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [dryRunning, setDryRunning] = useState(false);
  const [planningError, setPlanningError] = useState<ApiError | null>(null);
  const [dryRunError, setDryRunError] = useState<ApiError | null>(null);
  const [generatedPlan, setGeneratedPlan] = useState<GeneratedPlan | null>(null);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [savedDryRun, setSavedDryRun] = useState<SavedDryRun | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [devices, setDevices] = useState<Device[]>([]);
  const [editor, setEditor] = useState<PolicyEditor>(() =>
    emptyEditor(selectedDeviceId),
  );

  useEffect(() => {
    let active = true;
    setAudits({ status: "loading" });
    setPolicies({ status: "loading" });

    void Promise.allSettled([getAuditReports(selectedSubnet ?? undefined), loadPolicyRows()]).then(
      ([auditResult, policyResult]) => {
        if (!active) {
          return;
        }
        setAudits(
          auditResult.status === "fulfilled"
            ? { status: "ready", data: auditResult.value }
            : { status: "error", error: toApiError(auditResult.reason) },
        );
        if (policyResult.status === "fulfilled") {
          setPolicies({ status: "ready", data: policyResult.value });
          setSelectedPolicyIds((selected) =>
            selected.filter((id) =>
              policyResult.value.some((row) => row.summary.id === id),
            ),
          );
        } else {
          setPolicies({ status: "error", error: toApiError(policyResult.reason) });
          setSelectedPolicyIds([]);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [reloadVersion, selectedSubnet]);

  useEffect(() => {
    let active = true;
    void getDevices(selectedSubnet ? { subnet: selectedSubnet } : {}).then(
      (items) => {
        if (active) setDevices(items);
      },
      () => {
        if (active) setDevices([]);
      },
    );
    return () => {
      active = false;
    };
  }, [selectedSubnet]);

  useEffect(() => {
    const auditId = selectedAuditId ? Number(selectedAuditId) : null;
    setAuditFindingsKey(auditId);
    if (auditId === null) {
      setAuditFindings({ status: "loading" });
      return;
    }
    let active = true;
    setAuditFindings({ status: "loading" });
    void getAuditFindings(auditId).then(
      (data) => {
        if (active) {
          setAuditFindings({ status: "ready", data });
        }
      },
      (error: unknown) => {
        if (active) {
          setAuditFindings({ status: "error", error: toApiError(error) });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [selectedAuditId]);

  const selectedAudit =
    audits.status === "ready"
      ? audits.data.find((audit) => audit.id === Number(selectedAuditId))
      : undefined;
  const visibleAudits = useMemo(
    () =>
      audits.status === "ready"
        ? audits.data.filter((audit) => {
            if (
              selectedSubnet &&
              (audit.network_subnet ?? audit.summary?.network_subnet) !==
                selectedSubnet
            ) {
              return false;
            }
            if (
              selectedDeviceId !== null &&
              audit.device_id !== null &&
              audit.device_id !== selectedDeviceId
            ) {
              return false;
            }
            return true;
          })
        : [],
    [audits, selectedSubnet, selectedDeviceId],
  );

  const visiblePolicies = useMemo(
    () =>
      policies.status === "ready" && selectedDeviceId !== null
        ? policies.data.filter((row) => {
            const target = row.detail.status === "ready" ? row.detail.data.target : null;
            return target === null || Number(target) === selectedDeviceId;
          })
        : policies.status === "ready"
          ? policies.data
          : [],
    [policies, selectedDeviceId],
  );
  const matchingFindings =
    auditFindings.status === "ready" && auditFindingsKey === Number(selectedAuditId)
      ? auditFindings.data.filter((finding) =>
          /tracking|telemetry/i.test(finding.title || ""),
        )
      : [];
  const selectedPolicies = useMemo(
    () =>
      policies.status === "ready"
        ? policies.data.filter((row) => selectedPolicyIds.includes(row.summary.id))
        : [],
    [policies, selectedPolicyIds],
  );

  const createPlan = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPlanningError(null);
    setGeneratedPlan(null);
    if (!selectedAuditId) {
      setPlanningError(new Error("Select a saved audit report before generating a plan."));
      return;
    }
    if (!planningConfirmed) {
      setPlanningError(new Error("Confirm that policy planning will save proposed policies."));
      return;
    }

    setPlanning(true);
    try {
      const result = await generatePolicyPlan(Number(selectedAuditId));
      setGeneratedPlan({
        auditId: Number(selectedAuditId),
        policyIds: result.policies,
      });
      setReloadVersion((version) => version + 1);
    } catch (error) {
      setPlanningError(toApiError(error));
    } finally {
      setPlanning(false);
    }
  };

  const createDryRun = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setDryRunError(null);
    setDryRunResult(null);
    setSavedDryRun(null);
    if (selectedPolicyIds.length === 0) {
      setDryRunError(new Error("Select at least one saved policy for dry-run evaluation."));
      return;
    }
    if (!dryRunConfirmed) {
      setDryRunError(new Error("Confirm that dry-run evaluation will save a plan record."));
      return;
    }

    setDryRunning(true);
    try {
      const result = await runPolicyDryRun(selectedPolicyIds);
      setDryRunResult(result);
      setSavedDryRun({
        plan: { status: "loading" },
        impact: { status: "loading" },
      });
      const [planResult, impactResult] = await Promise.allSettled([
        getSavedDryRunPlan(result.plan_id),
        getDryRunImpact(result.plan_id),
      ]);
      setSavedDryRun({
        plan:
          planResult.status === "fulfilled"
            ? { status: "ready", data: planResult.value }
            : { status: "error", error: toApiError(planResult.reason) },
        impact:
          impactResult.status === "fulfilled"
            ? { status: "ready", data: impactResult.value }
            : { status: "error", error: toApiError(impactResult.reason) },
      });
    } catch (error) {
      setDryRunError(toApiError(error));
    } finally {
      setDryRunning(false);
    }
  };

  const togglePolicy = (policyId: number) => {
    setSelectedPolicyIds((current) =>
      current.includes(policyId)
        ? current.filter((id) => id !== policyId)
        : [...current, policyId],
    );
    setDryRunResult(null);
    setSavedDryRun(null);
    setDryRunError(null);
    setDryRunConfirmed(false);
  };

  const openNewPolicy = () => {
    setEditor({ ...emptyEditor(selectedDeviceId), open: true });
  };

  const openEditPolicy = (row: PolicyRow) => {
    if (row.detail.status !== "ready") {
      setEditor({
        ...emptyEditor(selectedDeviceId),
        open: true,
        error:
          row.detail.status === "error"
            ? row.detail.error
            : new Error("Policy detail is still loading; try again shortly."),
      });
      return;
    }
    const detail = row.detail.data;
    setEditor({
      ...emptyEditor(detail.target_device_id ?? selectedDeviceId),
      open: true,
      editingId: detail.id,
      name: detail.name,
      description: detail.description ?? "",
      targetDeviceId: detail.target_device_id ?? null,
      enabled: detail.config.enabled,
      blockedDomains: (detail.config.blocked_domains ?? []).join("\n"),
      allowedDomains: (detail.config.allowed_domains ?? []).join("\n"),
    });
  };

  const parseDomains = (value: string) =>
    value
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);

  const savePolicy = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setEditor((current) => ({ ...current, busy: true, error: null, message: "" }));
    const payload = {
      name: editor.name,
      description: editor.description,
      target_device_id: editor.targetDeviceId,
      enabled: editor.enabled,
      blocked_domains: parseDomains(editor.blockedDomains),
      allowed_domains: parseDomains(editor.allowedDomains),
    };
    try {
      if (editor.editingId !== null) {
        await updatePolicy(editor.editingId, payload);
        setEditor((current) => ({
          ...current,
          busy: false,
          message: `Policy #${current.editingId} was updated.`,
        }));
      } else {
        const created = await createPolicy(payload);
        setEditor((current) => ({
          ...current,
          busy: false,
          editingId: created.id,
          message: `Policy #${created.id} was saved as a proposal.`,
        }));
      }
      setReloadVersion((version) => version + 1);
    } catch (error) {
      setEditor((current) => ({
        ...current,
        busy: false,
        error: toApiError(error),
      }));
    }
  };

  const removePolicy = async (policyId: number) => {
    if (editor.deleteConfirmId !== policyId) return;
    setEditor((current) => ({ ...current, busy: true, error: null, message: "" }));
    try {
      await deletePolicy(policyId);
      setEditor((current) => ({
        ...current,
        busy: false,
        deleteConfirmId: null,
        open: current.editingId === policyId ? false : current.open,
        editingId: current.editingId === policyId ? null : current.editingId,
        message: `Policy #${policyId} was deleted.`,
      }));
      setReloadVersion((version) => version + 1);
    } catch (error) {
      setEditor((current) => ({ ...current, busy: false, error: toApiError(error) }));
    }
  };

  return (
    <LocalizedTree>
    <section className="policy-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> DEVICE POLICY WORKSPACE</div>
          <h1>Device <span>policies.</span></h1>
          <p className="page-description">
            Create, edit and delete device-targeted DNS policies, generate proposals from audits, and evaluate saved policies against recorded data. Saved configuration is shown separately from enforcement state.
          </p>
          {(selectedSubnet || selectedDeviceId !== null) && (
            <p className="muted-copy">
              Active context: {selectedSubnet ? <span data-no-translate="true">{selectedSubnet}</span> : "all networks"}
              {selectedDeviceId !== null ? ` · device #${selectedDeviceId}` : " · all devices"}
              <button type="button" className="secondary-button" onClick={() => clearNetworkContext()}>
                Clear device selection
              </button>
            </p>
          )}
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => setReloadVersion((version) => version + 1)}
          disabled={audits.status === "loading" || policies.status === "loading"}
        >
          <Icon name="refresh" size={16} />
          <span>Refresh plans</span>
        </button>
      </div>

      <div className="policy-safety-note">
        <Icon name="lock" size={16} />
        <span>
          Planning writes proposed policies to the backend. Dry-run saves a plan record. Neither action approves, applies, enforces, or activates protection.
        </span>
      </div>

      <section className="panel policy-editor-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">SAVED CONFIGURATION</div>
            <h2>{editor.editingId !== null ? `Edit policy #${editor.editingId}` : "Create a device policy"}</h2>
          </div>
          <button className="secondary-button" type="button" onClick={openNewPolicy}>
            <Icon name="shield" size={15} /> New policy
          </button>
        </div>
        <p className="policy-action-description">
          Only genuinely supported controls are offered: DNS block and allow rules, an enabled flag, and an optional target device. Internet access controls and schedules are unavailable and are never stored as active controls.
        </p>
        {editor.open ? (
          <form className="policy-form policy-create-form" onSubmit={(event) => void savePolicy(event)}>
            <div className="policy-form-grid">
              <label className="filter-control">
                <span>Name</span>
                <input
                  value={editor.name}
                  maxLength={128}
                  required
                  onChange={(event) => setEditor((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label className="filter-control">
                <span>Target device</span>
                <select
                  value={editor.targetDeviceId ?? ""}
                  onChange={(event) =>
                    setEditor((current) => ({
                      ...current,
                      targetDeviceId: event.target.value ? Number(event.target.value) : null,
                    }))
                  }
                >
                  <option value="">All devices / network scope</option>
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.hostname || device.ip_address || `Device #${device.id}`}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="filter-control">
              <span>Description / rationale</span>
              <textarea
                value={editor.description}
                rows={2}
                onChange={(event) => setEditor((current) => ({ ...current, description: event.target.value }))}
              />
            </label>
            <div className="policy-form-grid">
              <label className="filter-control">
                <span>Blocked domains (one per line)</span>
                <textarea
                  value={editor.blockedDomains}
                  rows={4}
                  data-no-translate="true"
                  placeholder={"tracker.example.net\nads.example.com"}
                  onChange={(event) => setEditor((current) => ({ ...current, blockedDomains: event.target.value }))}
                />
              </label>
              <label className="filter-control">
                <span>Allowed domains (one per line)</span>
                <textarea
                  value={editor.allowedDomains}
                  rows={4}
                  data-no-translate="true"
                  placeholder={"needed.example.org"}
                  onChange={(event) => setEditor((current) => ({ ...current, allowedDomains: event.target.value }))}
                />
              </label>
            </div>
            <label className="policy-confirmation">
              <input
                type="checkbox"
                checked={editor.enabled}
                onChange={(event) => setEditor((current) => ({ ...current, enabled: event.target.checked }))}
              />
              <span>Policy is enabled in saved configuration (not enforcement state)</span>
            </label>
            {editor.error && <ErrorMessage error={editor.error} />}
            {editor.message && <div className="policy-action-success" role="status">{editor.message}</div>}
            <div className="policy-editor-actions">
              <button className="primary-button" type="submit" disabled={editor.busy || !editor.name.trim()}>
                {editor.busy ? "Saving…" : editor.editingId !== null ? "Save changes" : "Create proposal"}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => setEditor(emptyEditor(selectedDeviceId))}
                disabled={editor.busy}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="policy-empty-state compact-empty">
            <span className="empty-icon"><Icon name="shield" size={18} /></span>
            <strong>No policy selected for editing</strong>
            <span>Use “New policy” or the Edit action in the saved policy table.</span>
          </div>
        )}
        {!editor.open && editor.message && <div className="policy-action-success" role="status">{editor.message}</div>}
        {!editor.open && editor.error && <ErrorMessage error={editor.error} />}
      </section>

      <section className="policy-action-grid">
        <article className="panel policy-action-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">SAVED AUDIT REQUIRED</div>
              <h2>Generate policy plan</h2>
            </div>
            <span className="read-only-tag">SAVES POLICIES</span>
          </div>
          <p className="policy-action-description">
            The backend creates proposed policies from audit findings whose titles contain “tracking” or “telemetry”. Each request may create additional saved records if repeated; the API does not expose a deduplication guarantee. It returns policy IDs only, without a finding-to-policy mapping or rationale per policy.
          </p>
          <form className="policy-form" onSubmit={(event) => void createPlan(event)}>
            <label className="filter-control">
              <span>Completed audit report</span>
              <select
                value={selectedAuditId}
                onChange={(event) => {
                  setSelectedAuditId(event.target.value);
                  setPlanningError(null);
                  setGeneratedPlan(null);
                  setPlanningConfirmed(false);
                }}
                disabled={audits.status !== "ready" || visibleAudits.length === 0 || planning}
                required
              >
                <option value="">
                  {audits.status === "loading"
                    ? "Loading audit reports…"
                    : audits.status === "error"
                      ? "Audit reports unavailable"
                      : visibleAudits.length === 0
                        ? "No saved audit reports for the selected network"
                        : "Choose a saved audit"}
                </option>
                {audits.status === "ready" && visibleAudits.map((audit) => (
                  <option value={audit.id} key={audit.id}>
                    {auditScope(audit.scope)} audit · #{audit.id} · {formatDate(audit.created_at)}
                  </option>
                ))}
              </select>
            </label>
            {audits.status === "error" && <ErrorMessage error={audits.error} />}
            {selectedAudit && (
              <div className="policy-audit-selection">
                <span>Selected saved report</span>
                <strong>#{selectedAudit.id} · {auditScope(selectedAudit.scope)}</strong>
                <span>{formatDate(selectedAudit.created_at)}</span>
                {auditFindingsKey === selectedAudit.id && auditFindings.status === "loading" && (
                  <span className="policy-inline-loading"><LoadingValue /> Checking findings…</span>
                )}
                {auditFindingsKey === selectedAudit.id && auditFindings.status === "error" && (
                  <ErrorMessage error={auditFindings.error} />
                )}
                {auditFindingsKey === selectedAudit.id && auditFindings.status === "ready" && (
                  <span>
                    {matchingFindings.length} finding{matchingFindings.length === 1 ? "" : "s"} match the backend’s current generation rule.
                  </span>
                )}
              </div>
            )}
            <label className="policy-confirmation">
              <input
                type="checkbox"
                checked={planningConfirmed}
                onChange={(event) => setPlanningConfirmed(event.target.checked)}
                disabled={planning}
              />
              <span>I understand this action creates and saves proposed policies.</span>
            </label>
            <button
              className="primary-button"
              type="submit"
              disabled={
                planning ||
                !planningConfirmed ||
                audits.status !== "ready" ||
                visibleAudits.length === 0 ||
                !selectedAuditId
              }
            >
              <Icon name="shield" size={16} />
              <span>{planning ? "Generating plan…" : "Generate and save plan"}</span>
            </button>
          </form>
          {planningError && (
            <div className="policy-action-error" role="alert">
              <strong>Policy plan was not confirmed</strong>
              <ErrorMessage error={planningError} />
            </div>
          )}
          {generatedPlan && (
            <div className="policy-action-success" role="status">
              <strong>Policy planning response received for audit #{generatedPlan.auditId}</strong>
              {generatedPlan.policyIds.length > 0 ? (
                <span>
                  Backend returned {generatedPlan.policyIds.length} saved policy ID{generatedPlan.policyIds.length === 1 ? "" : "s"}: {generatedPlan.policyIds.map((id) => `#${id}`).join(", ")}.
                </span>
              ) : (
                <span>The backend returned no policy IDs for this report. No proposed policies were reported as created.</span>
              )}
            </div>
          )}
        </article>

        <article className="panel policy-action-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">RECORDED DATA PROJECTION</div>
              <h2>Dry-run selected policies</h2>
            </div>
            <span className="read-only-tag">SAVES PLAN RECORD</span>
          </div>
          <p className="policy-action-description">
            The dry-run computes projected query counts from recorded DNS events. It does not configure a DNS backend or block traffic.
          </p>
          {policies.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Loading saved policies…</span></div>
          ) : policies.status === "error" ? (
            <div className="policy-list-error">
              <p>Saved policies are unavailable.</p>
              <ErrorMessage error={policies.error} />
            </div>
          ) : visiblePolicies.length === 0 ? (
            <div className="policy-empty-state">
              <span className="empty-icon"><Icon name="shield" size={18} /></span>
              <strong>No saved policies</strong>
              <span>Generate a policy plan from a saved audit report first.</span>
            </div>
          ) : (
            <form className="dry-run-form" onSubmit={(event) => void createDryRun(event)}>
              <fieldset className="policy-selection">
                <legend>Select saved policies for this projection</legend>
                {visiblePolicies.map((row) => (
                  <label className="policy-select-row" key={row.summary.id}>
                    <input
                      type="checkbox"
                      checked={selectedPolicyIds.includes(row.summary.id)}
                      onChange={() => togglePolicy(row.summary.id)}
                      disabled={dryRunning}
                    />
                    <span className="policy-select-copy">
                      <strong>
                        {row.summary.name
                          ? <span data-no-translate="true">{row.summary.name}</span>
                          : `Policy #${row.summary.id}`}
                      </strong>
                      <span>
                        #{row.summary.id} · {row.summary.risk || "Risk unavailable"}
                      </span>
                    </span>
                    <span className={`policy-status ${statusClass(row.summary.status)}`}>
                      {row.summary.status || "UNKNOWN"}
                    </span>
                  </label>
                ))}
              </fieldset>
              <div className="policy-detail-list">
                {selectedPolicies.map((row) => (
                  <details className="policy-detail" key={row.summary.id}>
                    <summary>Policy #{row.summary.id} details</summary>
                    {row.detail.status === "loading" ? (
                      <div className="panel-state"><LoadingValue /></div>
                    ) : row.detail.status === "error" ? (
                      <ErrorMessage error={row.detail.error} />
                    ) : (
                      <dl>
                        <div><dt>Name</dt><dd>{row.detail.data.name || "Not provided"}</dd></div>
                        <div><dt>Action</dt><dd>{row.detail.data.action || "Not provided"}</dd></div>
                        <div><dt>Risk</dt><dd>{row.detail.data.risk || "Not provided"}</dd></div>
                        <div><dt>Reversible</dt><dd>{row.detail.data.reversible ? "Reported reversible" : "Not reported as reversible"}</dd></div>
                        <div><dt>Target</dt><dd>{row.detail.data.target_device_id ? `Device #${row.detail.data.target_device_id}` : "Network scope"}</dd></div>
                        <div><dt>Enabled in saved config</dt><dd>{row.detail.data.config.enabled ? "Yes" : "No"}</dd></div>
                        <div><dt>Enforcement state</dt><dd>{row.detail.data.status}</dd></div>
                      </dl>
                    )}
                  </details>
                ))}
              </div>
              <div className="policy-projection-warning">
                Projection logic reads Advertising, Tracking/Analytics, and Telemetry DNS events and excludes exact domains google.com, microsoft.com, and apple.com. The API does not include per-policy attribution or a complete affected-domain list.
              </div>
              <label className="policy-confirmation">
                <input
                  type="checkbox"
                  checked={dryRunConfirmed}
                  onChange={(event) => setDryRunConfirmed(event.target.checked)}
                  disabled={dryRunning}
                />
                <span>I understand this action creates and saves a dry-run plan record.</span>
              </label>
              <button
                className="primary-button"
                type="submit"
                disabled={dryRunning || selectedPolicyIds.length === 0 || !dryRunConfirmed}
              >
                <Icon name="pulse" size={16} />
                <span>{dryRunning ? "Evaluating projection…" : "Run and save dry-run"}</span>
              </button>
            </form>
          )}
          {dryRunError && (
            <div className="policy-action-error" role="alert">
              <strong>Dry-run was not confirmed</strong>
              <ErrorMessage error={dryRunError} />
            </div>
          )}
          {dryRunResult && (
            <div className="dry-run-result" role="status">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">DRY-RUN RESPONSE</div>
                  <h3>Saved plan #{dryRunResult.plan_id}</h3>
                </div>
                <span className="policy-status policy-status-pending">PROJECTION ONLY</span>
              </div>
              <div className="dry-run-metrics">
                <div><span>POLICIES INCLUDED</span><strong>{dryRunResult.plan.policies.length}</strong></div>
                <div><span>AFFECTED QUERIES</span><strong>{dryRunResult.plan.affected_queries}</strong></div>
                <div><span>UNIQUE DOMAINS</span><strong>{dryRunResult.plan.unique_domains}</strong></div>
                <div><span>PROJECTED BLOCKED QUERIES</span><strong>{dryRunResult.impact.projected_blocked_queries}</strong></div>
              </div>
              <p>{dryRunResult.impact.note}</p>
              <p className="policy-result-limitation">
                This is a backend projection based on recorded data, not an enforcement result. No policy was approved or applied.
              </p>
              {savedDryRun && (
                <div className="saved-plan-confirmation">
                  <strong>Persisted plan record check</strong>
                  {savedDryRun.plan.status === "loading" || savedDryRun.impact.status === "loading" ? (
                    <span><LoadingValue /> Reading saved plan…</span>
                  ) : (
                    <>
                      {savedDryRun.plan.status === "ready" && savedDryRun.impact.status === "ready" ? (
                        <>
                          <span>Saved plan #{savedDryRun.plan.data.id} was returned by the plan endpoint.</span>
                          <span>
                            Stored plan values: {typeof savedDryRun.plan.data.plan?.policies?.length === "number"
                              ? `${savedDryRun.plan.data.plan.policies.length} policies`
                              : "policy count unavailable"} · {typeof savedDryRun.plan.data.plan?.affected_queries === "number"
                              ? `${savedDryRun.plan.data.plan.affected_queries} affected queries`
                              : "affected-query count unavailable"} · {typeof savedDryRun.plan.data.plan?.unique_domains === "number"
                              ? `${savedDryRun.plan.data.plan.unique_domains} unique domains`
                              : "unique-domain count unavailable"}.
                          </span>
                          <span>
                            Stored projected blocked queries: {typeof savedDryRun.impact.data?.projected_blocked_queries === "number"
                              ? savedDryRun.impact.data.projected_blocked_queries
                              : "Unknown"}
                            {savedDryRun.impact.data?.note ? ` · ${savedDryRun.impact.data.note}` : ""}
                          </span>
                        </>
                      ) : (
                        <>
                          {savedDryRun.plan.status === "error" && <ErrorMessage error={savedDryRun.plan.error} />}
                          {savedDryRun.impact.status === "error" && <ErrorMessage error={savedDryRun.impact.error} />}
                          <span>The dry-run response was successful, but persisted-plan details could not be fully reloaded.</span>
                        </>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </article>
      </section>

      <section className="panel policy-overview">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">BACKEND-SAVED RECORDS</div>
            <h2>Saved policies</h2>
          </div>
          {policies.status === "ready" && <span className="read-only-tag">{visiblePolicies.length} TOTAL</span>}
        </div>
        <p className="policy-action-description">
          Status and available details below are read from the policy APIs. This page provides no approval, apply, or enforcement controls.
        </p>
        {policies.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Loading saved policies…</span></div>
        ) : policies.status === "error" ? (
          <div className="policy-list-error">
            <ErrorMessage error={policies.error} />
          </div>
        ) : visiblePolicies.length === 0 ? (
          <div className="policy-empty-state">
            <span className="empty-icon"><Icon name="shield" size={18} /></span>
            <strong>No policies in the backend</strong>
            <span>Policy records will appear here after policy planning creates them.</span>
          </div>
        ) : (
          <div className="inventory-table-wrap">
            <table className="device-table policy-table">
              <thead>
                <tr><th>POLICY</th><th>ID</th><th>TARGET</th><th>CONFIG</th><th>ENFORCEMENT</th><th>RULES</th><th>CONTROLS</th></tr>
              </thead>
              <tbody>
                {visiblePolicies.map((row) => (
                  <tr key={row.summary.id}>
                    <td className="policy-name-cell">
                      {row.summary.name
                        ? <span data-no-translate="true">{row.summary.name}</span>
                        : "Name unavailable"}
                    </td>
                    <td>#{row.summary.id}</td>
                    <td>
                      {row.detail.status === "ready"
                        ? row.detail.data.target_device_id
                          ? `Device #${row.detail.data.target_device_id}`
                          : "Network scope"
                        : "Loading"}
                    </td>
                    <td>
                      {row.detail.status === "ready"
                        ? row.detail.data.config.enabled ? "Enabled" : "Disabled"
                        : "Loading"}
                    </td>
                    <td>
                      <span className={`policy-status ${statusClass(row.summary.status)}`}>
                        {row.summary.status || "UNKNOWN"}
                      </span>
                    </td>
                    <td>
                      {row.detail.status === "ready"
                        ? `${(row.detail.data.config.blocked_domains ?? []).length} block / ${(row.detail.data.config.allowed_domains ?? []).length} allow`
                        : "Loading"}
                    </td>
                    <td>
                      <div className="policy-row-actions">
                        <button className="text-link" type="button" onClick={() => openEditPolicy(row)}>Edit</button>
                        <button
                          className="text-link danger-link"
                          type="button"
                          onClick={() =>
                            setEditor((current) => ({
                              ...current,
                              deleteConfirmId:
                                current.deleteConfirmId === row.summary.id
                                  ? null
                                  : row.summary.id,
                              error: null,
                            }))
                          }
                        >
                          Delete
                        </button>
                        {editor.deleteConfirmId === row.summary.id && (
                          <div className="policy-delete-confirm">
                            <span>Delete policy #{row.summary.id}?</span>
                            <button className="danger-button" type="button" onClick={() => void removePolicy(row.summary.id)} disabled={editor.busy}>
                              Confirm delete
                            </button>
                            <button className="secondary-button" type="button" onClick={() => setEditor((current) => ({ ...current, deleteConfirmId: null }))}>
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {generatedPlan && generatedPlan.policyIds.length > 0 && (
          <p className="policy-linkage-note">
            This session received policy IDs from audit #{generatedPlan.auditId}: {generatedPlan.policyIds.map((id) => `#${id}`).join(", ")}. The backend does not persist or expose this audit-to-policy linkage.
          </p>
        )}
      </section>

      <p className="policy-limitations">
        Saved policies expose target, enabled state and supported DNS rule configuration. Enforcement state is reported separately and never inferred from a saved policy. Dry-run responses report aggregate counts without per-policy attribution. Approval, apply and rollback are handled on the Enforcement readiness page with explicit confirmation.
      </p>
    </section>
    </LocalizedTree>
  );
}
