export type ApiError = Error & {
  status?: number;
};

export type ResourceState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: ApiError };

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
};

export type Device = {
  id: number;
  ip_address: string;
  mac_address: string | null;
  hostname: string | null;
  vendor: string | null;
  discovery_source: string | null;
  first_seen: string;
  last_seen: string;
  metadata: Record<string, unknown> | null;
};

export type DeviceClassification = {
  device_id: number;
  category: string;
  confidence: number;
  reasons: string[];
  vendor_identified: boolean;
};

export type DiscoveryResult = {
  ip_address: string;
  mac_address: string | null;
  hostname: string | null;
  discovery_source: string;
  sources?: string[];
};

export type DiscoveryResponse = {
  discovered: number;
  subnet: string;
};

export type LocalNetworkInfo = {
  interface: string | null;
  ip_address: string | null;
  gateway: string | null;
  subnet: string | null;
};

export type RouterTestResponse = {
  ip: string;
  reachable: boolean;
  network_reachable: boolean;
  management_interface_available: boolean;
};

export type RouterCapabilities = {
  router_ip: string;
  network_reachable: boolean;
  management_interface_available: boolean;
  reachable: boolean;
  dhcp_leases: string;
  connected_devices: string;
  management_protocols: string[];
  authentication_required: string;
  adguard_home_configured?: boolean;
};

export type RouterDevicesResponse = {
  router_ip: string;
  status: "available" | "unsupported" | "authentication_required" | "access_denied" | "timeout" | "error";
  authentication_required: boolean | string;
  devices: DiscoveryResult[];
};

export type DnsProviderStatus = {
  provider: string | null;
  state: "healthy" | "not_configured" | "unreachable" | "unauthorized" | "timeout" | "unsupported_api" | "malformed_response" | "provider_unavailable";
  message?: string;
  capabilities: string[];
  unsupported: string[];
  version?: string | null;
  authentication?: string;
  query_log?: string;
  statistics?: string;
  filtering?: string;
  config?: Record<string, boolean | number | string | null>;
};

export type DnsSyncResult = {
  provider: string | null;
  fetched: number;
  inserted: number;
  duplicates: number;
  skipped: number;
  state: string;
};

export type DnsSummary = {
  total: number;
  unique_domains: number;
  by_category: Record<string, number>;
  blocked?: number;
  allowed?: number;
  blocking_percentage?: number | null;
  unknown_blocked_status?: number;
  top_domains?: { domain: string; count: number }[];
  top_blocked_domains?: { domain: string; count: number }[];
  by_client?: { client: string; count: number }[];
  by_source?: Record<string, number>;
  timeline?: { hour: string; count: number }[];
  category_evidence?: Record<string, { evidence: string; confidence: string }>;
};

export type DnsDomainCount = {
  domain: string;
  count: number;
  category: string;
};

export type DnsDeviceCount = {
  device_id: number | null;
  count: number;
};

export type DnsEvent = {
  id: number;
  domain: string;
  category: string | null;
  device_id: number | null;
  timestamp: string;
  query_type?: string | null;
  blocked?: boolean | null;
  client?: string | null;
  client_name?: string | null;
  reason?: string | null;
  rules?: string[];
  upstream?: string | null;
  source?: string;
  confidence?: string | null;
};

export type AuditReport = {
  id: number;
  scope: string;
  created_at: string;
};

export type AuditDetail = {
  id: number;
  scope: string;
  summary: {
    devices?: number;
    findings?: number;
  } | null;
  findings_count: number;
};

export type AuditFinding = {
  id: string;
  device_id: number | null;
  title: string;
  description: string;
  severity: string;
  detection_rule: string;
  evidence: string[];
  timestamp: string;
  recommended_next_step: string;
};

export type AuditRunResponse = {
  audit_id: number;
  findings: number;
  summary: {
    devices: number;
    findings: number;
  };
};

export type PolicySummary = {
  id: number;
  name: string;
  risk: string;
  status: string;
};

export type PolicyDetail = {
  id: number;
  name: string;
  action: string;
  risk: string;
  reversible: boolean;
};

export type PolicyPlanResponse = {
  policies: number[];
};

export type DryRunResult = {
  plan_id: number;
  plan: {
    policies: number[];
    affected_queries: number;
    unique_domains: number;
  };
  impact: {
    projected_blocked_queries: number;
    note: string;
  };
};

export type SavedDryRunPlan = {
  id: number;
  plan: {
    policies?: number[];
    affected_queries?: number;
    unique_domains?: number;
  } | null;
};

export type DryRunImpact = {
  projected_blocked_queries?: number;
  note?: string;
} | null;

export type EnforcementStatus = {
  available: boolean;
  backend: string | null;
};

export type RecoveryStatus = {
  recovery_ready: boolean;
  interrupted_executions: number;
};

export type SnapshotSummary = {
  id: number;
  backend: string | null;
  created_at: string;
  checksum: string | null;
};

export type SnapshotDetail = {
  id: number;
  state: Record<string, unknown> | null;
  checksum: string | null;
  integrity_ok: boolean;
};

export type PolicyApprovalStatus = {
  status: string;
  approver: string | null;
  approved_at: string | null;
  plan_id: number | null;
};

export type PolicyExecutionStatus = {
  status: string;
  details: Record<string, unknown> | null;
};

export type PolicyRollbackStatus = {
  policy_id: number;
  status: string;
  rollback_ready: boolean;
};

export type PolicyVerificationStatus = {
  policy_id: number;
  status: string;
  reason: string;
};

export type BackendCapabilities = {
  configured_backend: string | null;
  available: boolean;
  status: string;
};
