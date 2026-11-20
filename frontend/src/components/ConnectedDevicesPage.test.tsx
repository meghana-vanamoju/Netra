import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocalizationProvider } from "../localization";
import type { ConnectedDevice } from "../types";
import {
  applyNetworkControl,
  createNetworkControlPlan,
  getConnectedDevices,
  getNetworkTopologyStatus,
  verifyNetworkControl,
} from "../api";
import { ConnectedDevicesPage } from "./ConnectedDevicesPage";

vi.mock("../api", () => ({
  applyNetworkControl: vi.fn(),
  createNetworkControlPlan: vi.fn(),
  getConnectedDevices: vi.fn(),
  getNetworkTopologyStatus: vi.fn(),
  verifyNetworkControl: vi.fn(),
}));

const network = {
  uplink: {
    connected: true,
    connection_type: "ethernet",
    interface: "enp3s0f1",
    ip_address: "192.168.88.12",
    gateway: "192.168.88.1",
    subnet: "192.168.88.0/24",
  },
  hotspot: {
    active: true,
    interface: "wlp2s0",
    ip_address: "10.42.0.1",
    subnet: "10.42.0.0/24",
    connection: "Netra hotspot",
  },
  connected_device_count: 1,
  clients: [],
  enforcement: {
    status: "ready",
    configuration_ready: true,
    enabled: true,
    dry_run: false,
    privilege_model: "restricted_local_helper",
    backend_cap_net_admin: "missing",
    helper_status: "available",
    helper_authorized: true,
    helper_socket_path: "/run/netra/network-enforcement.sock",
    helper_error: null,
    nftables_binary_available: true,
    nftables_inspection_status: "available",
    nftables_write_permission_status: "not_verified",
    apply_permitted: true,
    mutation_permitted: true,
    firewall_rules_installed: null,
    firewall_rules_verified: null,
    physical_connectivity_status: "not_tested" as const,
    physical_connectivity_confirmed: false as const,
    interface: "wlp2s0",
    table: "netra",
    warnings: [],
  },
  warnings: [],
  access_control_authorization: "loopback_only",
  observed_at: "2026-11-19T10:00:00",
};

const allowedDevice = {
  device_id: 7,
  name: "My phone",
  ip_address: "10.42.0.24",
  mac_address: "AA:BB:CC:DD:EE:24",
  hotspot_interface: "wlp2s0",
  network_subnet: "10.42.0.0/24",
  first_seen: "2026-11-19T09:00:00",
  last_seen: "2026-11-19T10:00:00",
  connection_status: "connected" as const,
  internet_access: "allowed" as const,
  enforcement_status: "not_applied",
  identity_status: "validated",
  sources: ["wifi_station", "dhcp_lease"],
  verification_status: "rules_verified" as const,
};

const response = (device: ConnectedDevice) => ({
  devices: [device],
  connected_device_count: 1,
  warnings: [],
});

const plan = {
  plan_id: 11,
  plan: {
    action: "block_internet" as const,
    device: {
      device_id: 7,
      ip_address: "10.42.0.24",
      mac_address: "AA:BB:CC:DD:EE:24",
      interface: "wlp2s0",
    },
    warnings: ["Only this verified device is targeted."],
    apply_allowed: true,
    apply_blockers: [],
  },
  impact: {
    affected_devices: [7],
    scope: "single validated device",
    network_change: false,
    note: "Dry run only.",
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getNetworkTopologyStatus).mockResolvedValue(network);
  vi.mocked(getConnectedDevices).mockResolvedValue(response(allowedDevice));
  vi.mocked(createNetworkControlPlan).mockResolvedValue(plan);
  vi.mocked(applyNetworkControl).mockResolvedValue({
    status: "applied",
    verified: true,
    internet_access: "blocked",
    configuration_ready: true,
    firewall_rules_installed: true,
    firewall_rules_verified: true,
    physical_connectivity_status: "not_tested",
    physical_connectivity_confirmed: false,
  });
  vi.mocked(verifyNetworkControl).mockResolvedValue({
    device_id: 7,
    internet_access: "blocked",
    verified: true,
  });
});

afterEach(cleanup);

function renderPage() {
  return render(
    <LocalizationProvider>
      <ConnectedDevicesPage />
    </LocalizationProvider>,
  );
}

describe("ConnectedDevicesPage", () => {
  it("renders detected uplink, hotspot, and distinct connection/access states", async () => {
    renderPage();

    expect(await screen.findByText(/enp3s0f1/)).toBeTruthy();
    expect(screen.getByText(/wlp2s0.*10\.42\.0\.1/)).toBeTruthy();
    expect(screen.getByText("Physical connectivity: not tested")).toBeTruthy();
    expect(screen.getByText("My phone")).toBeTruthy();
    expect(screen.getByText("Connected", { selector: ".device-connection-state" })).toBeTruthy();
    expect(screen.getByText("No Netra block rules", { selector: ".device-access-state" })).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Install firewall restrictions for My phone" })).toBeTruthy();
  });

  it("shows a dry-run plan and updates only after apply and verification succeed", async () => {
    vi.mocked(getConnectedDevices)
      .mockResolvedValueOnce(response(allowedDevice))
      .mockResolvedValueOnce(
        response({
          ...allowedDevice,
          internet_access: "blocked",
          enforcement_status: "applied",
        }),
      );
    renderPage();

    fireEvent.click(
      await screen.findByRole("switch", { name: "Install firewall restrictions for My phone" }),
    );
    expect(await screen.findByText("Only this verified device is targeted.")).toBeTruthy();
    expect(createNetworkControlPlan).toHaveBeenCalledWith(7, "block_internet");

    fireEvent.change(screen.getByLabelText("Confirming user"), {
      target: { value: "Meghana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Block Internet" }));

    await waitFor(() => {
      expect(applyNetworkControl).toHaveBeenCalledWith(
        7,
        11,
        "block_internet",
        "Meghana",
      );
      expect(verifyNetworkControl).toHaveBeenCalledWith(7);
    });
    expect(await screen.findByText(/Firewall rules were verified for My phone/)).toBeTruthy();
    expect(screen.getByText(/physical connectivity was not tested/i)).toBeTruthy();
    await waitFor(() =>
      expect(
        screen.getByRole("switch", { name: "Remove firewall restrictions for My phone" }).getAttribute("aria-checked"),
      ).toBe("true"),
    );
  });

  it("does not show a successful blocked state when the apply API fails", async () => {
    vi.mocked(applyNetworkControl).mockRejectedValue(new Error("Firewall command failed"));
    renderPage();

    fireEvent.click(
      await screen.findByRole("switch", { name: "Install firewall restrictions for My phone" }),
    );
    await screen.findByText("Only this verified device is targeted.");
    fireEvent.change(screen.getByLabelText("Confirming user"), {
      target: { value: "Meghana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Block Internet" }));

    expect(await screen.findByText("Firewall command failed")).toBeTruthy();
    expect(
      screen.getByRole("switch", { name: "Install firewall restrictions for My phone" }).getAttribute("aria-checked"),
    ).toBe("false");
  });

  it("keeps apply disabled when the backend dry-run plan blocks it", async () => {
    vi.mocked(createNetworkControlPlan).mockResolvedValue({
      ...plan,
      plan: {
        ...plan.plan,
        apply_allowed: false,
        apply_blockers: ["NETRA_NETWORK_ENFORCEMENT_DRY_RUN is true"],
      },
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("switch", { name: "Install firewall restrictions for My phone" }),
    );
    expect(await screen.findByText("Apply is disabled")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Confirm Block Internet" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(applyNetworkControl).not.toHaveBeenCalled();
  });
});
