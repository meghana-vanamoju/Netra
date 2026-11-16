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
};

export type DiscoveryResponse = {
  discovered: number;
  subnet: string;
};

export type DnsSummary = {
  total: number;
  unique_domains: number;
  by_category: Record<string, number>;
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

export type BackendCapabilities = {
  configured_backend: string | null;
  available: boolean;
  status: string;
};
