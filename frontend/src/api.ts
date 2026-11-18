import type {
  AdGuardDiagnostics,
  AdGuardStatus,
  AuditDetail,
  AuditFinding,
  AuditReport,
  AuditRunResponse,
  BackendCapabilities,
  BandwidthInterface,
  BandwidthSample,
  BandwidthStatus,
  DashboardSummary,
  DeviceClassification,
  Device,
  DiscoveryResponse,
  DiscoveryResult,
  DnsDeviceCount,
  DnsDomainCount,
  DnsEvent,
  DnsProviderStatus,
  DnsSummary,
  DnsSyncResult,
  DryRunImpact,
  DryRunResult,
  EnforcementReadiness,
  EnforcementStatus,
  HealthResponse,
  LocalNetworkInfo,
  PolicyConfigInput,
  PolicyDetail,
  PolicyDraft,
  PolicyApprovalStatus,
  PolicyExecutionStatus,
  PolicyPlanResponse,
  PolicyRollbackStatus,
  PolicySummary,
  PolicyVerificationStatus,
  PrivacyScore,
  RecoveryStatus,
  SavedDryRunPlan,
  SnapshotDetail,
  SnapshotSummary,
  RouterCapabilities,
  RouterDevicesResponse,
  RouterTestResponse,
} from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const API_BASE_URL = (configuredBaseUrl || "http://127.0.0.1:8084").replace(
  /\/+$/,
  "",
);

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 10_000,
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
      signal: controller.signal,
    });
  } catch {
    const message = controller.signal.aborted
      ? `The request to ${API_BASE_URL} timed out.`
      : `Could not connect to ${API_BASE_URL}. Check the backend URL and that the backend is running.`;
    throw new ApiRequestError(message, 0);
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const body: { detail?: unknown } = await response.json();
      if (typeof body.detail === "string" && body.detail.trim()) {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        const info = body.detail as { message?: unknown; state?: unknown };
        if (typeof info.message === "string" && info.message.trim()) {
          detail = info.message;
        } else if (typeof info.state === "string" && info.state.trim()) {
          detail = `DNS provider state: ${info.state}`;
        }
      }
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new ApiRequestError(detail, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiRequestError(
      "The backend returned an invalid JSON response.",
      response.status,
    );
  }
}

export function getHealth() {
  return requestJson<HealthResponse>("/api/health");
}

export function getDatabaseHealth() {
  return requestJson<{ status: string }>("/api/db/health");
}

export function getDevices(options: { live?: boolean; subnet?: string } = {}) {
  const query = new URLSearchParams({ limit: "200" });
  if (options.live) query.set("live", "true");
  if (options.subnet) query.set("subnet", options.subnet);
  return requestJson<Device[]>(`/api/devices?${query.toString()}`);
}

export function getClassifications() {
  return requestJson<DeviceClassification[]>("/api/classifications");
}

export function classifyDevice(deviceId: number) {
  return requestJson<DeviceClassification>(`/api/devices/${deviceId}/classify`, {
    method: "POST",
  });
}

export function runDiscovery(subnet: string) {
  // URLSearchParams already escapes "/". Decode first so a value that is
  // already percent-encoded is not encoded a second time (% -> %25).
  let canonicalSubnet = subnet.trim();
  try {
    canonicalSubnet = decodeURIComponent(canonicalSubnet);
  } catch {
    // Keep the original value; the backend validates and reports bad CIDRs.
  }
  const query = new URLSearchParams({ subnet: canonicalSubnet });
  return requestJson<DiscoveryResponse>(
    `/api/discovery/run?${query.toString()}`,
    { method: "POST" },
    30_000,
  );
}

export function getLocalNetworkInfo() {
  return requestJson<LocalNetworkInfo>("/api/discovery/network");
}

export function testRouter(ip: string) {
  const query = new URLSearchParams({ ip });
  return requestJson<RouterTestResponse>(`/api/router/test?${query}`, {
    method: "POST",
  });
}

export function getRouterCapabilities(ip: string) {
  const query = new URLSearchParams({ ip });
  return requestJson<RouterCapabilities>(`/api/router/capabilities?${query}`);
}

export function getRouterDevices(ip: string) {
  const query = new URLSearchParams({ ip });
  return requestJson<RouterDevicesResponse>(
    `/api/router/devices?${query}`,
    { method: "POST" },
    15_000,
  );
}

export function getDiscoveryResults(subnet?: string) {
  const suffix = subnet ? `?${new URLSearchParams({ subnet }).toString()}` : "";
  return requestJson<DiscoveryResult[]>(`/api/discovery/results${suffix}`);
}

export function getDnsSummary(deviceId?: number, subnet?: string) {
  const query = new URLSearchParams();
  if (deviceId !== undefined) {
    query.set("device_id", String(deviceId));
  }
  if (subnet) {
    query.set("subnet", subnet);
  }
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<DnsSummary>(`/api/dns/analytics/summary${suffix}`);
}

export function getDnsProviderStatus() {
  return requestJson<DnsProviderStatus>("/api/dns/providers/status");
}

export function getDnsProviderStatistics() {
  return requestJson<Record<string, unknown>>("/api/dns/providers/statistics");
}

export function getDnsProviderFiltering() {
  return requestJson<{ enabled: boolean; user_rules: string[]; filter_count: number | null }>(
    "/api/dns/providers/filtering",
  );
}

export function syncDnsEvents() {
  return requestJson<DnsSyncResult>("/api/dns/events/sync", { method: "POST" });
}

export function getDnsDomains(limit = 20, deviceId?: number, subnet?: string) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (deviceId !== undefined) query.set("device_id", String(deviceId));
  if (subnet) query.set("subnet", subnet);
  return requestJson<DnsDomainCount[]>(`/api/dns/analytics/domains?${query}`);
}

export function getDnsDeviceCounts(subnet?: string) {
  const query = new URLSearchParams();
  if (subnet) query.set("subnet", subnet);
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<DnsDeviceCount[]>(`/api/dns/analytics/devices${suffix}`);
}

export function getDnsEvents({
  limit = 50,
  offset = 0,
  deviceId,
  linked,
  clientIp,
  subnet,
  domain,
}: {
  limit?: number;
  offset?: number;
  deviceId?: number;
  linked?: boolean;
  clientIp?: string;
  subnet?: string;
  domain?: string;
} = {}) {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (deviceId !== undefined) {
    query.set("device_id", String(deviceId));
  }
  if (linked !== undefined) query.set("linked", String(linked));
  if (clientIp) query.set("client_ip", clientIp);
  if (subnet) query.set("subnet", subnet);
  if (domain) query.set("domain", domain);
  return requestJson<DnsEvent[]>(`/api/dns/events?${query}`);
}

export function setDnsFilteringRule(
  domain: string,
  action: "block" | "unblock" | "allow" | "remove",
  confirm: boolean,
) {
  return requestJson<Record<string, unknown>>("/api/dns/providers/filtering/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain, action, confirm }),
  });
}

export function getAdGuardStatus(ip: string) {
  const query = new URLSearchParams({ ip });
  return requestJson<AdGuardStatus>(`/api/router/adguard/status?${query}`);
}

export function getAuditReports(subnet?: string) {
  const query = new URLSearchParams();
  if (subnet) query.set("subnet", subnet);
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<AuditReport[]>(`/api/audits${suffix}`);
}

export function getAudit(auditId: number) {
  return requestJson<AuditDetail>(`/api/audits/${auditId}`);
}

export function getAuditFindings(auditId: number) {
  return requestJson<AuditFinding[]>(`/api/audits/${auditId}/findings`);
}

export function runAudit(scope: "network" | "device", deviceId?: number, subnet?: string) {
  const query = new URLSearchParams({ scope });
  if (scope === "device" && deviceId !== undefined) {
    query.set("device_id", String(deviceId));
  }
  if (scope === "network" && subnet) {
    query.set("subnet", subnet);
  }
  return requestJson<AuditRunResponse>(
    `/api/audits/run?${query}`,
    { method: "POST" },
    60_000,
  );
}

export function getBackendCapabilities() {
  return requestJson<BackendCapabilities>("/api/backend/capabilities");
}

export function getPolicies() {
  return requestJson<PolicySummary[]>("/api/policies");
}

export function getPolicy(policyId: number) {
  return requestJson<PolicyDetail>(`/api/policies/${policyId}`);
}

export function generatePolicyPlan(auditId: number) {
  const query = new URLSearchParams({ audit_id: String(auditId) });
  return requestJson<PolicyPlanResponse>(`/api/policies/plan?${query}`, {
    method: "POST",
  });
}

export function runPolicyDryRun(policyIds: number[]) {
  return requestJson<DryRunResult>("/api/policies/dry-run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policyIds),
  });
}

export function getSavedDryRunPlan(planId: number) {
  return requestJson<SavedDryRunPlan>(`/api/policies/dry-run/${planId}`);
}

export function getDryRunImpact(planId: number) {
  return requestJson<DryRunImpact>(`/api/policies/dry-run/${planId}/impact`);
}

export function getEnforcementStatus() {
  return requestJson<EnforcementStatus>("/api/enforcement/status");
}

export function getRecoveryStatus() {
  return requestJson<RecoveryStatus>("/api/recovery/status");
}

export function getSnapshots() {
  return requestJson<SnapshotSummary[]>("/api/snapshots");
}

export function getSnapshot(snapshotId: number) {
  return requestJson<SnapshotDetail>(`/api/snapshots/${snapshotId}`);
}

export function getPolicyApprovalStatus(policyId: number) {
  return requestJson<PolicyApprovalStatus>(`/api/policies/${policyId}/approval`);
}

export function getPolicyExecutionStatus(policyId: number) {
  return requestJson<PolicyExecutionStatus>(`/api/policies/${policyId}/execution`);
}

export function getPolicyRollbackStatus(policyId: number) {
  return requestJson<PolicyRollbackStatus>(
    `/api/policies/${policyId}/rollback-status`,
  );
}

export function getPolicyVerificationStatus(policyId: number) {
  return requestJson<PolicyVerificationStatus>(
    `/api/verification/policy/${policyId}`,
  );
}

export function approvePolicy(policyId: number, planId: number, confirm = true) {
  return requestJson<Record<string, unknown>>(
    `/api/policies/${policyId}/approve?plan_id=${planId}&confirm=${confirm}`,
    { method: "POST" },
  );
}

export function applyPolicy(policyId: number) {
  return requestJson<Record<string, unknown>>(`/api/policies/${policyId}/apply`, {
    method: "POST",
  });
}

export function rollbackSnapshot(snapshotId: number, confirm = true) {
  return requestJson<Record<string, unknown>>(
    `/api/snapshots/${snapshotId}/rollback?confirm=${confirm}`,
    { method: "POST" },
  );
}

export function getDashboardSummary(subnet?: string) {
  const suffix = subnet ? `?${new URLSearchParams({ subnet }).toString()}` : "";
  return requestJson<DashboardSummary>(`/api/dashboard/summary${suffix}`);
}

export function getBandwidthInterfaces() {
  return requestJson<BandwidthInterface[]>("/api/bandwidth/interfaces");
}

export function getBandwidthStatus(iface?: string) {
  const suffix = iface ? `?${new URLSearchParams({ interface: iface }).toString()}` : "";
  return requestJson<BandwidthStatus>(`/api/bandwidth/status${suffix}`);
}

export function sampleBandwidth(iface?: string, intervalMs?: number) {
  const query = new URLSearchParams();
  if (iface) query.set("interface", iface);
  if (intervalMs !== undefined) query.set("interval_ms", String(intervalMs));
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<BandwidthSample>(`/api/bandwidth/sample${suffix}`, { method: "POST" }, 10_000);
}

export function getBandwidthHistory(iface?: string, limit = 60) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (iface) query.set("interface", iface);
  return requestJson<{ interface: string; retention_samples: number; returned: number; samples: BandwidthSample[] }>(
    `/api/bandwidth/history?${query.toString()}`,
  );
}

export function getAdGuardDiagnostics(subnet?: string, deviceId?: number) {
  const query = new URLSearchParams();
  if (subnet) query.set("subnet", subnet);
  if (deviceId !== undefined) query.set("device_id", String(deviceId));
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<AdGuardDiagnostics>(`/api/diagnostics/adguard${suffix}`);
}

export function getEnforcementReadiness() {
  return requestJson<EnforcementReadiness>("/api/enforcement/readiness");
}

export function getPrivacyScore(subnet?: string, deviceId?: number) {
  const query = new URLSearchParams();
  if (subnet) query.set("subnet", subnet);
  if (deviceId !== undefined) query.set("device_id", String(deviceId));
  const search = query.toString();
  const suffix = search ? `?${search}` : "";
  return requestJson<PrivacyScore>(`/api/privacy/score${suffix}`);
}

export function createPolicy(payload: PolicyConfigInput) {
  return requestJson<PolicyDetail>("/api/policies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updatePolicy(policyId: number, payload: PolicyConfigInput) {
  return requestJson<PolicyDetail>(`/api/policies/${policyId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deletePolicy(policyId: number) {
  return requestJson<{ status: string; policy_id: number }>(
    `/api/policies/${policyId}?confirm=true`,
    { method: "DELETE" },
  );
}

export function previewPolicies(auditId: number) {
  return requestJson<{ audit_id: number; drafts: PolicyDraft[]; saved: boolean }>(
    `/api/policies/preview?audit_id=${auditId}`,
    { method: "POST" },
  );
}

export function refreshDnsFilters() {
  return requestJson<Record<string, unknown>>("/api/dns/providers/filtering/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
}

export function createProviderSnapshot() {
  return requestJson<{ id: number; checksum: string; backend: string; rules: number; type: string }>(
    "/api/snapshots/from-provider",
    { method: "POST" },
  );
}

export function deleteSnapshot(snapshotId: number) {
  return requestJson<{ status: string; snapshot_id: number }>(
    `/api/snapshots/${snapshotId}?confirm=true`,
    { method: "DELETE" },
  );
}
