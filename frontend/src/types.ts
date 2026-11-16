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
  };
  findings_count: number;
};

export type AuditFinding = {
  id: string;
  device_id: number | null;
  title: string;
  description: string;
  severity: string;
  timestamp: string;
};

export type BackendCapabilities = {
  configured_backend: string | null;
  available: boolean;
  status: string;
};
