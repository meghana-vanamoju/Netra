import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocalizationProvider } from "../localization";
import { DnsAnalyticsPage } from "./DnsAnalyticsPage";
import {
    getDevices,
    getDnsDeviceCounts,
    getDnsDomains,
    getDnsEvents,
    getDnsProviderFiltering,
    getDnsProviderStatus,
    getDnsSummary,
    setDnsFilteringRule,
    syncDnsEvents,
} from "../api";

vi.mock("../api", () => ({
    getDevices: vi.fn(),
    getDnsDeviceCounts: vi.fn(),
    getDnsDomains: vi.fn(),
    getDnsEvents: vi.fn(),
    getDnsProviderFiltering: vi.fn(),
    getDnsProviderStatus: vi.fn(),
    getDnsSummary: vi.fn(),
    setDnsFilteringRule: vi.fn(),
    syncDnsEvents: vi.fn(),
}));

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDnsSummary).mockResolvedValue({
        total: 2,
        unique_domains: 2,
        by_category: { Advertising: 1, Unknown: 1 },
        blocked: 1,
        allowed: 1,
    });
    vi.mocked(getDnsDomains).mockResolvedValue([
        { domain: "ads.example", count: 1, category: "Advertising" },
    ]);
    vi.mocked(getDnsDeviceCounts).mockResolvedValue([
        { device_id: 1, count: 2, blocked: 1, allowed: 1 },
        { device_id: null, count: 1, blocked: 0, allowed: 0 },
    ]);
    vi.mocked(getDevices).mockResolvedValue([
        {
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
        },
    ]);
    vi.mocked(getDnsEvents).mockResolvedValue([
        {
            id: 1,
            domain: "ads.example",
            category: "Advertising",
            device_id: 1,
            association_status: "linked",
            timestamp: "2026-11-18T10:04:00Z",
            blocked: true,
            device: { name: "phone", ip: "10.0.0.5", mac: "AA:BB:CC:DD:EE:55" },
        },
        {
            id: 2,
            domain: "unknown.example",
            category: "Unknown",
            device_id: null,
            association_status: "ambiguous",
            timestamp: "2026-11-18T10:03:00Z",
            blocked: null,
            device: null,
        },
    ]);
    vi.mocked(getDnsProviderStatus).mockResolvedValue({
        provider: "adguard-home",
        state: "healthy",
        capabilities: ["api_connectivity", "filtering"],
        unsupported: [],
    });
    vi.mocked(getDnsProviderFiltering).mockResolvedValue({
        enabled: true,
        user_rules: [],
        filter_count: 1,
    });
    vi.mocked(syncDnsEvents).mockResolvedValue({
        provider: "adguard-home",
        fetched: 0,
        inserted: 0,
        duplicates: 0,
        skipped: 0,
        state: "healthy",
    });
    vi.mocked(setDnsFilteringRule).mockResolvedValue({ status: "applied" });
});

afterEach(cleanup);

describe("DnsAnalyticsPage device and provider states", () => {
    it("presents linked IP/MAC and ambiguous unlinked events", async () => {
        render(
            <LocalizationProvider>
                <DnsAnalyticsPage />
            </LocalizationProvider>,
        );

        expect(await screen.findAllByText(/10\.0\.0\.5/)).toHaveLength(2);
        expect(screen.getByText(/AA:BB:CC:DD:EE:55/)).toBeTruthy();
        expect(screen.getByText("Ambiguous / unlinked")).toBeTruthy();
    });

    it("shows blocked and allowed per-device counts", async () => {
        render(
            <LocalizationProvider>
                <DnsAnalyticsPage />
            </LocalizationProvider>,
        );

        expect(await screen.findByText(/1 blocked · 1 allowed/)).toBeTruthy();
    });

    it("shows no-provider state without fabricated events", async () => {
        vi.mocked(getDnsProviderStatus).mockResolvedValue({
            provider: null,
            state: "not_configured",
            capabilities: [],
            unsupported: [],
        });
        vi.mocked(getDnsProviderFiltering).mockRejectedValue(new Error("Provider filtering unavailable"));

        render(
            <LocalizationProvider>
                <DnsAnalyticsPage />
            </LocalizationProvider>,
        );

        expect(await screen.findByText("No DNS provider configured")).toBeTruthy();
    });

    it("requires confirmation before submitting a block rule", async () => {
        render(
            <LocalizationProvider>
                <DnsAnalyticsPage />
            </LocalizationProvider>,
        );

        const domain = await screen.findByLabelText("Filtering domain");
        fireEvent.change(domain, { target: { value: "ads.example" } });
        const apply = screen.getByRole("button", { name: "Apply rule" });
        expect((apply as HTMLButtonElement).disabled).toBe(true);

        fireEvent.click(screen.getByLabelText(/I confirm this provider rule change/));
        expect((apply as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(apply);

        await waitFor(() => {
            expect(setDnsFilteringRule).toHaveBeenCalledWith("ads.example", "block", true);
        });
    });
});
