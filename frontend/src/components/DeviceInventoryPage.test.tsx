import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocalizationProvider } from "../localization";
import { DeviceInventoryPage } from "./DeviceInventoryPage";
import { getDevices, getClassifications } from "../api";

vi.mock("../api", () => ({
    getDevices: vi.fn(),
    getClassifications: vi.fn(),
    classifyDevice: vi.fn(),
}));

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDevices).mockResolvedValue([
        {
            id: 1,
            ip_address: "192.168.88.10",
            mac_address: "AA:BB:CC:DD:EE:10",
            hostname: "live-phone",
            vendor: null,
            discovery_source: "lan-discovery",
            first_seen: "2026-11-18T10:00:00Z",
            last_seen: "2026-11-18T10:05:00Z",
            is_current: true,
            network_subnet: "192.168.88.0/24",
            last_scan_at: "2026-11-18T10:05:00Z",
            scan_status: "complete",
            metadata: null,
        },
    ]);
    vi.mocked(getClassifications).mockResolvedValue([]);
});

afterEach(cleanup);

describe("DeviceInventoryPage live inventory", () => {
    it("requests live-only devices and renders no historical-row label", async () => {
        render(
            <LocalizationProvider>
                <DeviceInventoryPage />
            </LocalizationProvider>,
        );

        await waitFor(() => expect(getDevices).toHaveBeenCalledWith({ live: true }));
        expect(await screen.findByText("live-phone")).toBeTruthy();
        expect(screen.getByText(/Live discovery snapshot only/)).toBeTruthy();
    });
});
