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
  is_current?: boolean;
  network_subnet?: string | null;
  last_scan_at?: string | null;
  scan_status?: string | null;
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
  duration_seconds?: number;
  probes_attempted?: number;
  hosts_responding?: number;
  timeout_count?: number;
  probe_errors?: number;
  partial_results?: boolean;
  scan_status?: "complete" | "partial";
  coverage?: {
    hosts_in_subnet: number;
    hosts_probed: number;
    coverage_complete: boolean;
    unprobed_hosts: number;
  };
};

export type LocalNetworkInfo = {
  interface: string | null;
  ip_address: string | null;
  gateway: string | null;
  subnet: string | null;
};

export type NetworkTopologyStatus = {
  uplink: {
    connected: boolean;
    connection_type: string | null;
    interface: string | null;
    ip_address: string | null;
    gateway: string | null;
    subnet: string | null;
  };
  hotspot: {
    active: boolean;
    interface: string | null;
    ip_address: string | null;
    subnet: string | null;
    connection: string | null;
  };
  connected_device_count: number;
  clients: Array<{
    ip_address: string | null;
    mac_address: string;
    hostname: string | null;
    connection_status: string;
    identity_status: string;
    sources: string[];
  }>;
  enforcement: {
    status: string;
    configuration_ready: boolean;
    enabled: boolean;
    dry_run: boolean;
    privilege_model: string;
    backend_cap_net_admin: string;
    helper_status: string;
    helper_authorized: boolean;
    helper_socket_path: string;
    helper_error: { code: string; message: string } | null;
    nftables_binary_available: boolean | null;
    nftables_inspection_status: string;
    nftables_write_permission_status: string;
    apply_permitted: boolean;
    mutation_permitted: boolean;
    firewall_rules_installed: boolean | null;
    firewall_rules_verified: boolean | null;
    physical_connectivity_status: "not_tested";
    physical_connectivity_confirmed: false;
    interface: string | null;
    table: string;
    warnings: string[];
  };
  warnings: string[];
  access_control_authorization: string;
  observed_at: string;
};

export type ConnectedDevice = {
  device_id: number | null;
  name: string;
  ip_address: string | null;
  mac_address: string | null;
  hotspot_interface: string;
  network_subnet: string | null;
  first_seen: string | null;
  last_seen: string | null;
  connection_status: "connected" | "disconnected";
  internet_access:
  | "allowed"
  | "blocked"
  | "blocked_pending_verification"
  | "reconciliation_required"
  | "enforcement_error"
  | "identity_validation_required"
  | "unknown"
  | "pending"
  | string;
  enforcement_status: string;
  identity_status: string;
  sources: string[];
  enforcement_error?: unknown;
  verification_status?: "rules_verified" | "rules_unverified";
  firewall_rules_installed?: boolean;
  firewall_rules_verified?: boolean;
  physical_connectivity_status?: "not_tested";
  physical_connectivity_confirmed?: false;
};

export type ConnectedDevicesResponse = {
  devices: ConnectedDevice[];
  connected_device_count: number;
  warnings: string[];
  observed_at?: string;
};

export type NetworkControlAction = "block_internet" | "restore_internet";

export type NetworkControlPlanResponse = {
  plan_id: number;
  plan: {
    action: NetworkControlAction;
    device: {
      device_id: number;
      ip_address: string;
      mac_address: string;
      interface: string;
    };
    warnings: string[];
    apply_allowed: boolean;
    apply_blockers: string[];
  };
  impact: {
    affected_devices: number[];
    scope: string;
    network_change: boolean;
    note: string;
  };
};

export type NetworkControlApplyResponse = {
  status: string;
  verified: boolean;
  internet_access: "blocked" | "allowed" | "unknown";
  configuration_ready: boolean;
  firewall_rules_installed: boolean;
  firewall_rules_verified: boolean;
  physical_connectivity_status: "not_tested";
  physical_connectivity_confirmed: false;
};

export type NetworkControlVerifyResponse = {
  device_id: number;
  internet_access: string;
  verified: boolean;
  configuration_ready?: boolean;
  firewall_rules_installed?: boolean;
  firewall_rules_verified?: boolean;
  physical_connectivity_status?: "not_tested";
  physical_connectivity_confirmed?: false;
  verification?: Record<string, unknown>;
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

export type AdGuardStatus = {
  configured: boolean;
  provider_state: string;
  router_ip: string;
  filtering_enabled: boolean | null;
  filter_count: number | null;
  user_rule_count?: number;
  dhcp_inventory: string;
  network_wide_enforcement: "not_verified" | "verified";
  guidance: string[];
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
  blocked?: number;
  allowed?: number;
};

export type DnsEvent = {
  id: number;
  domain: string;
  category: string | null;
  device_id: number | null;
  device?: { name: string | null; ip: string; mac: string | null } | null;
  association_status?: "linked" | "ambiguous" | "unlinked";
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
  device_id?: number | null;
  network_subnet?: string | null;
  summary?: Record<string, unknown> | null;
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

export type PolicyConfig = {
  enabled: boolean;
  blocked_domains: string[];
  allowed_domains: string[];
  internet_access_control: string | null;
  dns_protection: string | null;
  schedule: string | null;
};

export type PolicyDetail = {
  id: number;
  name: string;
  description: string | null;
  target?: string | null;
  target_device_id?: number | null;
  action: string;
  risk: string;
  reversible: boolean;
  status: string;
  config: PolicyConfig;
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
  type?: string;
  size_bytes?: number;
};

export type SnapshotDetail = {
  id: number;
  backend?: string | null;
  created_at?: string;
  state: Record<string, unknown> | null;
  checksum: string | null;
  integrity_ok: boolean;
  type?: string;
  size_bytes?: number;
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

export type DashboardSummary = {
  selected_subnet: string | null;
  devices: { count: number; scope: string };
  discovery: {
    scanned: boolean;
    subnet?: string | null;
    discovered?: number;
    last_scan_at?: string | null;
    scan_status?: string;
    coverage?: {
      hosts_in_subnet: number;
      hosts_probed: number;
      coverage_complete: boolean;
      unprobed_hosts: number;
    };
    partial_results?: boolean;
  };
  dns: {
    total: number;
    allowed: number;
    blocked: number;
    blocking_percentage: number | null;
    unknown_blocked_status: number;
    available: boolean;
  };
  provider: {
    configured: boolean;
    state: string;
    provider: string | null;
    message?: string;
  };
  privacy: {
    score: number;
    explanation: string;
    tracking_events: number;
    unknown_events: number;
    latest_audit_id: number | null;
    latest_audit_created_at: string | null;
    latest_audit_scope: string | null;
  };
  enforcement: {
    provider_ready: boolean;
    network_wide_ready: boolean;
    state: string;
    snapshot_count: number;
  };
  bandwidth: {
    available: boolean;
    interface: string | null;
    scope: string;
    rx_bytes_per_second: number | null;
    tx_bytes_per_second: number | null;
    rx_bytes_total: number;
    tx_bytes_total: number;
    sample_count: number;
  };
};

export type BandwidthInterface = {
  name: string;
  active: boolean;
  rx_bytes_total: number;
  tx_bytes_total: number;
};

export type BandwidthSample = {
  interface: string;
  sampled_at: string;
  interval_seconds: number;
  rx_bytes_per_second: number;
  tx_bytes_per_second: number;
  rx_bytes_total: number;
  tx_bytes_total: number;
  rx_bytes_delta: number;
  tx_bytes_delta: number;
};

export type BandwidthStatus = {
  interface: string;
  active_interface: string | null;
  monitoring: boolean;
  sampling_interval_ms: number;
  retention_samples: number;
  sample_count: number;
  latest: BandwidthSample | null;
  cumulative: {
    rx_bytes: number;
    tx_bytes: number;
    rx_packets: number;
    tx_packets: number;
  };
  scope: string;
  message: string;
};

export type AdGuardDiagnostics = {
  provider: {
    configured: boolean;
    state: string;
    provider: string | null;
    version: string | null;
    authentication: string | null;
    capabilities: string[];
    unsupported: string[];
    message?: string;
    config?: Record<string, unknown>;
  };
  filtering: {
    available: boolean;
    state?: string;
    message?: string;
    data: { enabled: boolean; user_rules: string[]; filter_count: number | null } | null;
  };
  statistics: { available: boolean; state?: string; message?: string; data: Record<string, unknown> | null };
  enforcement: { backend: string | null; enabled: boolean; available: boolean };
  query_log: {
    recorded_events: number;
    linked_events: number;
    latest_timestamp: string | null;
    clients_identifiable: boolean;
  };
  router: {
    interface: string | null;
    local_ip: string | null;
    gateway: string | null;
    dhcp_dns_verified: boolean;
    dns_redirect_verified: boolean;
    note: string;
  };
  scope: {
    subnet: string | null;
    device_id: number | null;
    laptop_local_monitoring: boolean;
    router_wide_protection_verified: boolean;
  };
};

export type EnforcementReadiness = {
  provider_ready: boolean;
  network_wide_ready: boolean;
  provider_state: string;
  backend: string | null;
  enabled: boolean;
  filtering_available: boolean;
  snapshot_count: number;
  local_network: { interface: string | null; ip_address: string | null; gateway: string | null; subnet: string | null };
  required_permissions: string[];
  supported_modes: { mode: string; supported: boolean; scope: string }[];
  unsupported_modes: { mode: string; reason: string }[];
  warnings: string[];
};

export type PrivacyScore = {
  score: number;
  explanation: string;
  tracking_events: number;
  unknown_events: number;
  observed_events: number;
  scope: { subnet: string | null; device_id: number | null };
};

export type PolicyDraft = {
  name: string;
  action: string;
  target_device_id: number | null;
  risk: string;
  reason: string;
  detection_rule: string;
  evidence: string[];
  recommended_next_step: string;
};

export type PolicyConfigInput = {
  name: string;
  description: string;
  target_device_id: number | null;
  enabled: boolean;
  blocked_domains: string[];
  allowed_domains: string[];
};
