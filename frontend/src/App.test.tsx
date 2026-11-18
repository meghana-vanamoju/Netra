import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { getDatabaseHealth, getDashboardSummary, getHealth } from "./api";
import { LocalizationProvider } from "./localization";
import { NetworkProvider } from "./NetworkContext";
import { ThemeProvider } from "./theme";

vi.mock("./api", () => ({
  getHealth: vi.fn(),
  getDatabaseHealth: vi.fn(),
  getDashboardSummary: vi.fn(),
}));

function renderApp() {
  return render(
    <ThemeProvider>
      <LocalizationProvider>
        <NetworkProvider>
          <App />
        </NetworkProvider>
      </LocalizationProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.location.hash = "";
  window.sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  window.scrollTo = vi.fn();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  vi.mocked(getHealth).mockResolvedValue({
    status: "ok",
    service: "netra-backend",
    version: "0.1.0",
  } as never);
  vi.mocked(getDatabaseHealth).mockResolvedValue({ status: "ok" } as never);
  vi.mocked(getDashboardSummary).mockResolvedValue({
    selected_subnet: null,
    devices: { count: 0, scope: "latest discovery snapshot" },
    discovery: { scanned: false, subnet: null },
    dns: {
      total: 0,
      allowed: 0,
      blocked: 0,
      blocking_percentage: null,
      unknown_blocked_status: 0,
      available: true,
    },
    provider: { configured: false, state: "not_configured" },
    privacy: {
      score: null,
      explanation: "no observations recorded",
      tracking_events: 0,
      unknown_events: 0,
      latest_audit_id: null,
      latest_audit_created_at: null,
      latest_audit_scope: null,
    },
    enforcement: {
      provider_ready: false,
      network_wide_ready: false,
      state: "not_configured",
      snapshot_count: 0,
    },
    bandwidth: {
      available: false,
      interface: null,
      scope: "netra-host-interface",
      rx_bytes_per_second: null,
      tx_bytes_per_second: null,
      rx_bytes_total: null,
      tx_bytes_total: null,
      sample_count: 0,
    },
  } as never);
});

afterEach(cleanup);

describe("App API availability indicator", () => {
  it("shows API connected when service and database health both report ok", async () => {
    renderApp();

    expect(await screen.findByText("API connected")).toBeTruthy();
    expect(getHealth).toHaveBeenCalledOnce();
    expect(getDatabaseHealth).toHaveBeenCalledOnce();
  });

  it("shows API unavailable when the database health check fails", async () => {
    vi.mocked(getDatabaseHealth).mockRejectedValueOnce(new Error("Database unavailable"));

    renderApp();

    expect(await screen.findByText("API unavailable")).toBeTruthy();
    expect(screen.queryByText("API connected")).toBeNull();
  });
});
