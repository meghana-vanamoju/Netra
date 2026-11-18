import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocalizationProvider } from "../localization";
import { NetworkProvider } from "../NetworkContext";
import {
  applyPolicy,
  createPolicy,
  createProviderSnapshot,
  deletePolicy,
  deleteSnapshot,
  getAdGuardDiagnostics,
  getAudit,
  getAuditFindings,
  getAuditReports,
  getBandwidthHistory,
  getBandwidthInterfaces,
  getBandwidthStatus,
  getDashboardSummary,
  getDevices,
  getDnsEvents,
  getDnsProviderFiltering,
  getDnsProviderStatus,
  getEnforcementReadiness,
  getEnforcementStatus,
  getPolicy,
  getPolicyApprovalStatus,
  getPolicyExecutionStatus,
  getPolicyRollbackStatus,
  getPolicyVerificationStatus,
  getPolicies,
  getPrivacyScore,
  getRecoveryStatus,
  getSnapshot,
  getSnapshots,
  previewPolicies,
  refreshDnsFilters,
  rollbackSnapshot,
  sampleBandwidth,
  setDnsFilteringRule,
  syncDnsEvents,
  updatePolicy,
} from "../api";
import { AdGuardDiagnosticsPage } from "./AdGuardDiagnosticsPage";
import { BackupRecoveryPage } from "./BackupRecoveryPage";
import { BandwidthMonitorPage } from "./BandwidthMonitorPage";
import { DashboardPage } from "./DashboardPage";
import { EnforcementRecoveryPage } from "./EnforcementRecoveryPage";
import { PolicyPlanningPage } from "./PolicyPlanningPage";
import { PrivacyAuditPage } from "./PrivacyAuditPage";

vi.mock("../api", () => {
  class ApiRequestError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return {
    ApiRequestError,
    applyPolicy: vi.fn(),
    createPolicy: vi.fn(),
    createProviderSnapshot: vi.fn(),
    deletePolicy: vi.fn(),
    deleteSnapshot: vi.fn(),
    getAdGuardDiagnostics: vi.fn(),
    getAudit: vi.fn(),
    getAuditFindings: vi.fn(),
    getAuditReports: vi.fn(),
    getBandwidthHistory: vi.fn(),
    getBandwidthInterfaces: vi.fn(),
    getBandwidthStatus: vi.fn(),
    getDashboardSummary: vi.fn(),
    getDevices: vi.fn(),
    getDnsEvents: vi.fn(),
    getDnsProviderFiltering: vi.fn(),
    getDnsProviderStatus: vi.fn(),
    getEnforcementReadiness: vi.fn(),
    getEnforcementStatus: vi.fn(),
    getPolicy: vi.fn(),
    getPolicyApprovalStatus: vi.fn(),
    getPolicyExecutionStatus: vi.fn(),
    getPolicyRollbackStatus: vi.fn(),
    getPolicyVerificationStatus: vi.fn(),
    getPolicies: vi.fn(),
    getPrivacyScore: vi.fn(),
    getRecoveryStatus: vi.fn(),
    getSnapshot: vi.fn(),
    getSnapshots: vi.fn(),
    previewPolicies: vi.fn(),
    refreshDnsFilters: vi.fn(),
    rollbackSnapshot: vi.fn(),
    runAudit: vi.fn(),
    runPolicyDryRun: vi.fn(),
    sampleBandwidth: vi.fn(),
    setDnsFilteringRule: vi.fn(),
    syncDnsEvents: vi.fn(),
    updatePolicy: vi.fn(),
  };
});

const device = {
  id: 1,
  ip_address: "10.0.0.5",
  mac_address: "AA:BB:CC:DD:EE:55",
  hostname: "phone",
  vendor: null,
  discovery_source: "lan-discovery",
  first_seen: "2026-11-18T10:00:00Z",
  last_seen: "2026-11-18T10:05:00Z",
  is_current: true,
  metadata: null,
};

function renderPage(ui: React.ReactNode) {
  return render(
    <LocalizationProvider>
      <NetworkProvider>{ui}</NetworkProvider>
    </LocalizationProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();

  vi.mocked(getPolicies).mockResolvedValue([
    { id: 3, name: "Tracker block", risk: "Medium", status: "proposed" },
  ] as never);
  vi.mocked(getPolicy).mockResolvedValue({
    id: 3,
    name: "Tracker block",
    description: "Test policy",
    target: null,
    target_device_id: null,
    action: "custom_dns_filter",
    risk: "Medium",
    reversible: true,
    status: "proposed",
    config: {
      enabled: true,
      blocked_domains: ["tracker.example"],
      allowed_domains: [],
      internet_access_control: null,
      dns_protection: "provider_user_rules",
      schedule: null,
    },
  } as never);
  vi.mocked(getDevices).mockResolvedValue([device] as never);
  vi.mocked(getAuditReports).mockResolvedValue([] as never);
  vi.mocked(getAuditFindings).mockResolvedValue([] as never);
  vi.mocked(getAudit).mockResolvedValue({
    id: 4,
    scope: "network",
    summary: { devices: 1, findings: 1 },
    findings_count: 1,
  } as never);
  vi.mocked(getPrivacyScore).mockResolvedValue({
    score: 12,
    explanation: "based on observed events",
    tracking_events: 1,
    unknown_events: 0,
    observed_events: 5,
    scope: { subnet: null, device_id: null },
  } as never);
  vi.mocked(previewPolicies).mockResolvedValue({
    audit_id: 4,
    drafts: [],
    saved: false,
  } as never);
  vi.mocked(createPolicy).mockResolvedValue({ id: 9 } as never);
  vi.mocked(updatePolicy).mockResolvedValue({ id: 3 } as never);
  vi.mocked(deletePolicy).mockResolvedValue({ status: "deleted", policy_id: 3 } as never);

  vi.mocked(getSnapshots).mockResolvedValue([
    { id: 7, backend: "adguard", created_at: "2026-11-18T10:00:00Z", checksum: "abc123", type: "provider_configuration", size_bytes: 120 },
  ] as never);
  vi.mocked(getSnapshot).mockResolvedValue({
    id: 7,
    backend: "adguard",
    created_at: "2026-11-18T10:00:00Z",
    state: { user_rules: ["||ads.example^"] },
    checksum: "abc123",
    integrity_ok: true,
    type: "provider_configuration",
    size_bytes: 120,
  } as never);
  vi.mocked(createProviderSnapshot).mockResolvedValue({ id: 8, checksum: "def", backend: "adguard", rules: 1, type: "provider_configuration" } as never);
  vi.mocked(deleteSnapshot).mockResolvedValue({ status: "deleted", snapshot_id: 7 } as never);
  vi.mocked(rollbackSnapshot).mockResolvedValue({ status: "restored" } as never);

  vi.mocked(getBandwidthInterfaces).mockResolvedValue([
    { name: "eth0", active: true, rx_bytes_total: 100, tx_bytes_total: 50 },
  ] as never);
  vi.mocked(getBandwidthStatus).mockResolvedValue({
    interface: "eth0",
    active_interface: "eth0",
    monitoring: false,
    sampling_interval_ms: 1000,
    retention_samples: 240,
    sample_count: 0,
    latest: null,
    cumulative: { rx_bytes: 100, tx_bytes: 50, rx_packets: 2, tx_packets: 1 },
    scope: "netra-host-interface",
    message: "Traffic measured on the Netra host interface.",
  } as never);
  vi.mocked(getBandwidthHistory).mockResolvedValue({ interface: "eth0", retention_samples: 240, returned: 0, samples: [] } as never);
  vi.mocked(sampleBandwidth).mockResolvedValue({
    interface: "eth0",
    sampled_at: "2026-11-18T10:06:00Z",
    interval_seconds: 1,
    rx_bytes_per_second: 2048,
    tx_bytes_per_second: 1024,
    rx_bytes_total: 2148,
    tx_bytes_total: 1074,
    rx_bytes_delta: 2048,
    tx_bytes_delta: 1024,
  } as never);

  vi.mocked(getAdGuardDiagnostics).mockResolvedValue({
    provider: {
      configured: true,
      state: "healthy",
      provider: "adguard-home",
      version: "v0.107.0",
      authentication: "verified",
      capabilities: ["api_connectivity", "filtering"],
      unsupported: [],
    },
    filtering: { available: true, data: { enabled: true, user_rules: [], filter_count: 1 } },
    statistics: { available: true, data: { total_queries: 4 } },
    enforcement: { backend: "adguard", enabled: true, available: true },
    query_log: { recorded_events: 4, linked_events: 1, latest_timestamp: null, clients_identifiable: true },
    router: {
      interface: "eth0",
      local_ip: "10.0.0.2",
      gateway: "10.0.0.1",
      dhcp_dns_verified: false,
      dns_redirect_verified: false,
      note: "Router DHCP/DNS has not been independently verified.",
    },
    scope: { subnet: null, device_id: null, laptop_local_monitoring: true, router_wide_protection_verified: false },
  } as never);
  vi.mocked(getDnsProviderStatus).mockResolvedValue({ provider: "adguard-home", state: "healthy", capabilities: ["filtering"], unsupported: [] } as never);
  vi.mocked(getDnsProviderFiltering).mockResolvedValue({ enabled: true, user_rules: [], filter_count: 1 } as never);
  vi.mocked(getDnsEvents).mockResolvedValue([] as never);
  vi.mocked(syncDnsEvents).mockResolvedValue({ provider: "adguard-home", fetched: 1, inserted: 1, duplicates: 0, skipped: 0, state: "healthy" } as never);
  vi.mocked(setDnsFilteringRule).mockResolvedValue({ status: "applied" } as never);
  vi.mocked(refreshDnsFilters).mockResolvedValue({ status: "refreshed" } as never);

  vi.mocked(getEnforcementStatus).mockResolvedValue({ available: true, backend: "adguard", enabled: true, provider_state: "healthy" } as never);
  vi.mocked(getEnforcementReadiness).mockResolvedValue({
    provider_ready: true,
    network_wide_ready: false,
    provider_state: "healthy",
    backend: "adguard",
    enabled: true,
    filtering_available: true,
    snapshot_count: 1,
    local_network: { interface: "eth0", ip_address: "10.0.0.2", gateway: "10.0.0.1", subnet: "10.0.0.0/24" },
    required_permissions: ["Configured DNS provider API credentials"],
    supported_modes: [{ mode: "provider_dns_filtering", supported: true, scope: "DNS provider server" }],
    unsupported_modes: [{ mode: "router_dhcp_dns_configuration", reason: "No verified router write capability" }],
    warnings: ["Provider filtering is server-side."],
  } as never);
  vi.mocked(getRecoveryStatus).mockResolvedValue({ recovery_ready: true, interrupted_executions: 0 } as never);
  vi.mocked(getPolicyApprovalStatus).mockResolvedValue({ status: "approved", approver: "tester", approved_at: null, plan_id: 1 } as never);
  vi.mocked(getPolicyExecutionStatus).mockResolvedValue({ status: "not_applied", details: {} } as never);
  vi.mocked(getPolicyRollbackStatus).mockResolvedValue({ status: "not_applied", rollback_ready: true } as never);
  vi.mocked(getPolicyVerificationStatus).mockResolvedValue({ status: "not_verified", reason: "No provider evidence" } as never);
  vi.mocked(applyPolicy).mockResolvedValue({ status: "applied" } as never);

  vi.mocked(getDashboardSummary).mockResolvedValue({
    selected_subnet: null,
    devices: { count: 3, scope: "latest discovery snapshot" },
    discovery: { scanned: false, subnet: null },
    dns: { total: 10, allowed: 8, blocked: 2, blocking_percentage: 20, unknown_blocked_status: 0, available: true },
    provider: { configured: true, state: "healthy", provider: "adguard-home" },
    privacy: { score: 12, explanation: "based on observed events", tracking_events: 1, unknown_events: 0, latest_audit_id: 4, latest_audit_created_at: "2026-11-18T10:00:00Z", latest_audit_scope: "network" },
    enforcement: { provider_ready: true, network_wide_ready: false, state: "healthy", snapshot_count: 1 },
    bandwidth: { available: true, interface: "eth0", scope: "netra-host-interface", rx_bytes_per_second: 100, tx_bytes_per_second: 50, rx_bytes_total: 1000, tx_bytes_total: 500, sample_count: 1 },
  } as never);
});

afterEach(cleanup);

describe("Dashboard and host telemetry", () => {
  it("renders live dashboard values and withholds router-wide verification", async () => {
    renderPage(<DashboardPage />);

    expect(await screen.findByText("3")).toBeTruthy();
    expect(screen.getByText("Not verified")).toBeTruthy();
    expect(screen.getByText("netra-host-interface")).toBeTruthy();
  });

  it("takes an explicit local interface sample", async () => {
    renderPage(<BandwidthMonitorPage />);

    const sample = await screen.findByRole("button", { name: "Take 1-second sample" });
    fireEvent.click(sample);

    await waitFor(() => expect(sampleBandwidth).toHaveBeenCalledWith("eth0", 1000));
    expect(await screen.findByText(/Measured eth0 over 1s/)).toBeTruthy();
  });
});

describe("Backup and recovery", () => {
  it("captures provider configuration and requires checkbox confirmation to delete", async () => {
    renderPage(<BackupRecoveryPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Snapshot #7/i }));
    expect(await screen.findByText("CHECKSUM MATCH")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Create provider snapshot/i }));
    await waitFor(() => expect(createProviderSnapshot).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("I confirm deleting this local snapshot."));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteSnapshot).toHaveBeenCalledWith(8));
  });
});

describe("AdGuard diagnostics", () => {
  it("runs the reversible temporary-rule workflow", async () => {
    renderPage(<AdGuardDiagnosticsPage />);

    expect(await screen.findByText("Safe AdGuard test procedure")).toBeTruthy();
    expect(screen.getByText("NOT VERIFIED")).toBeTruthy();

    fireEvent.click(screen.getByLabelText(/I confirm adding and later removing the temporary test rule/));
    fireEvent.click(screen.getByRole("button", { name: "Add temporary rule" }));
    await waitFor(() =>
      expect(setDnsFilteringRule).toHaveBeenCalledWith("netra-test.blocked.invalid", "block", true),
    );

    fireEvent.click(screen.getByRole("button", { name: "Sync and check query log" }));
    await waitFor(() => expect(syncDnsEvents).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Remove temporary rule" }));
    await waitFor(() =>
      expect(setDnsFilteringRule).toHaveBeenCalledWith("netra-test.blocked.invalid", "unblock", true),
    );
  });
});

describe("Policy management", () => {
  it("creates a device policy with only supported DNS controls", async () => {
    renderPage(<PolicyPlanningPage />);

    fireEvent.click(await screen.findByRole("button", { name: /New policy/i }));
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "Phone tracker block" } });
    fireEvent.change(screen.getByLabelText("Blocked domains (one per line)"), {
      target: { value: "tracker.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create proposal" }));

    await waitFor(() =>
      expect(createPolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Phone tracker block",
          blocked_domains: ["tracker.example"],
          enabled: true,
        }),
      ),
    );
  });

  it("requires explicit confirmation before deleting a policy", async () => {
    renderPage(<PolicyPlanningPage />);

    const deleteButton = await screen.findByRole("button", { name: "Delete" });
    fireEvent.click(deleteButton);
    expect(deletePolicy).not.toHaveBeenCalled();

    fireEvent.click(await screen.findByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(deletePolicy).toHaveBeenCalledWith(3));
  });
});

describe("Enforcement readiness and privacy audit", () => {
  it("reports unsupported router controls and gates apply behind confirmation", async () => {
    renderPage(<EnforcementRecoveryPage />);

    expect(await screen.findByText(/router_dhcp_dns_configuration/)).toBeTruthy();
    expect(screen.getByText("Not verified")).toBeTruthy();

    const apply = screen.getByRole("button", { name: "Apply selected policy" });
    expect((apply as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("I confirm that this policy may change DNS filtering rules."));
    expect((apply as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(apply);
    await waitFor(() => expect(applyPolicy).toHaveBeenCalledWith(3));
  });

  it("shows an observation-based privacy score and a non-persistent policy preview", async () => {
    vi.mocked(getAuditReports).mockResolvedValue([
      { id: 4, scope: "network", created_at: "2026-11-18T10:00:00Z" },
    ] as never);
    vi.mocked(getPrivacyScore).mockResolvedValue({
      score: 12,
      explanation: "no observations recorded",
      tracking_events: 0,
      unknown_events: 0,
      observed_events: 0,
      scope: { subnet: null, device_id: null },
    } as never);

    renderPage(<PrivacyAuditPage />);

    expect(await screen.findByText("Privacy score")).toBeTruthy();
    expect(screen.getByText("No DNS observations: this is no data, not a verified absence of risk.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Preview policies" }));
    await waitFor(() => expect(previewPolicies).toHaveBeenCalledWith(4));
    expect(screen.getByText("No evidence-backed policy drafts were produced for this report.")).toBeTruthy();
  });
});
