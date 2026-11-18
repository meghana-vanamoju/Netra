import type {
  AuditDetail,
  AuditFinding,
  AuditReport,
  AuditRunResponse,
  BackendCapabilities,
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
  EnforcementStatus,
  HealthResponse,
  LocalNetworkInfo,
  PolicyDetail,
  PolicyApprovalStatus,
  PolicyExecutionStatus,
  PolicyPlanResponse,
  PolicyRollbackStatus,
  PolicySummary,
  PolicyVerificationStatus,
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

export function getDevices() {
  return requestJson<Device[]>("/api/devices?limit=200");
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
    180_000,
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

export function getDiscoveryResults() {
  return requestJson<DiscoveryResult[]>("/api/discovery/results");
}

export function getDnsSummary(deviceId?: number) {
  const query = new URLSearchParams();
  if (deviceId !== undefined) {
    query.set("device_id", String(deviceId));
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

export function getDnsDomains(limit = 20) {
  const query = new URLSearchParams({ limit: String(limit) });
  return requestJson<DnsDomainCount[]>(`/api/dns/analytics/domains?${query}`);
}

export function getDnsDeviceCounts() {
  return requestJson<DnsDeviceCount[]>("/api/dns/analytics/devices");
}

export function getDnsEvents({
  limit = 50,
  offset = 0,
  deviceId,
}: {
  limit?: number;
  offset?: number;
  deviceId?: number;
} = {}) {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (deviceId !== undefined) {
    query.set("device_id", String(deviceId));
  }
  return requestJson<DnsEvent[]>(`/api/dns/events?${query}`);
}

export function getAuditReports() {
  return requestJson<AuditReport[]>("/api/audits");
}

export function getAudit(auditId: number) {
  return requestJson<AuditDetail>(`/api/audits/${auditId}`);
}

export function getAuditFindings(auditId: number) {
  return requestJson<AuditFinding[]>(`/api/audits/${auditId}/findings`);
}

export function runAudit(scope: "network" | "device", deviceId?: number) {
  const query = new URLSearchParams({ scope });
  if (scope === "device" && deviceId !== undefined) {
    query.set("device_id", String(deviceId));
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
