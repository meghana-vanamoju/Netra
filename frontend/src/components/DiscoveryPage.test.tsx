import { act } from "react";
import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DiscoveryPage } from "./DiscoveryPage";
import { LocalizationProvider } from "../localization";
import {
    getDevices,
    getDiscoveryResults,
    getLocalNetworkInfo,
    getRouterCapabilities,
    getRouterDevices,
    runDiscovery,
    testRouter,
} from "../api";
import type { DiscoveryResponse, DiscoveryResult } from "../types";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

vi.mock("../api", () => ({
    getDevices: vi.fn(),
    getDiscoveryResults: vi.fn(),
    getLocalNetworkInfo: vi.fn(),
    getRouterCapabilities: vi.fn(),
    getRouterDevices: vi.fn(),
    runDiscovery: vi.fn(),
    testRouter: vi.fn(),
}));

const discoveredDevice: DiscoveryResult = {
    ip_address: "192.168.88.10",
    mac_address: "AA:BB:CC:DD:EE:FF",
    hostname: null,
    discovery_source: "arp",
};

function renderPage() {
    return render(
        <LocalizationProvider>
            <DiscoveryPage />
        </LocalizationProvider>,
    );
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDevices).mockResolvedValue([]);
    vi.mocked(getDiscoveryResults).mockResolvedValue([]);
    vi.mocked(getLocalNetworkInfo).mockResolvedValue({
        interface: "wlan0",
        ip_address: "192.168.88.20",
        gateway: "192.168.88.1",
        subnet: "192.168.88.0/24",
    });
    vi.mocked(getRouterCapabilities).mockResolvedValue({} as never);
    vi.mocked(getRouterDevices).mockResolvedValue({} as never);
    vi.mocked(testRouter).mockResolvedValue({} as never);
});

afterEach(() => {
    cleanup();
});

describe("DiscoveryPage LAN scanning", () => {
    it("shows progress, blocks duplicate submits, reports results, and refreshes inventory", async () => {
        let resolveScan!: (response: DiscoveryResponse) => void;
        vi.mocked(runDiscovery).mockReturnValue(
            new Promise((resolve) => {
                resolveScan = resolve;
            }),
        );
        vi.mocked(getDiscoveryResults)
            .mockResolvedValueOnce([])
            .mockResolvedValueOnce([discoveredDevice]);

        renderPage();
        const scanButton = (await screen.findByRole("button", { name: "LAN discovery" })) as HTMLButtonElement;
        await waitFor(() => expect(scanButton.disabled).toBe(false));
        const form = scanButton.closest("form");
        if (!form) throw new Error("LAN discovery form was not rendered");

        fireEvent.submit(form);
        fireEvent.submit(form);

        expect(runDiscovery).toHaveBeenCalledTimes(1);
        const busyButtons = screen.getAllByRole("button", { name: "Discovering…" });
        expect(busyButtons).toHaveLength(2);
        expect(busyButtons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
        expect(screen.getByText("Scanning LAN")).toBeTruthy();
        expect(screen.getByText(/elapsed/)).toBeTruthy();

        await act(async () => {
            resolveScan({
                discovered: 1,
                subnet: "192.168.88.0/24",
                duration_seconds: 1.4,
                probes_attempted: 64,
                hosts_responding: 1,
                timeout_count: 2,
                probe_errors: 0,
                partial_results: true,
            });
        });

        expect(await screen.findByText("device discovered")).toBeTruthy();
        expect(screen.getByText(/1\.4s/)).toBeTruthy();
        expect(screen.getByText("scan duration")).toBeTruthy();
        expect(screen.getByText("Partial results")).toBeTruthy();
        expect(await screen.findByText(discoveredDevice.ip_address)).toBeTruthy();
        await waitFor(() => {
            expect(getDiscoveryResults).toHaveBeenCalledTimes(2);
            expect(getDevices).toHaveBeenCalledTimes(2);
        });
    });

    it.each([
        {
            message: "The request to http://127.0.0.1:8084 timed out.",
            status: 0,
            title: "Discovery request timed out",
        },
        {
            message: "Could not connect to http://127.0.0.1:8084.",
            status: 0,
            title: "Backend connection failed",
        },
        {
            message: "The LAN scan could not be completed by this host.",
            status: 503,
            title: "Discovery service error",
        },
    ])("distinguishes scan failures: $title", async ({ message, status, title }) => {
        const error = Object.assign(new Error(message), { status });
        vi.mocked(runDiscovery).mockRejectedValueOnce(error);

        renderPage();
        const scanButton = (await screen.findByRole("button", { name: "LAN discovery" })) as HTMLButtonElement;
        await waitFor(() => expect(scanButton.disabled).toBe(false));
        const form = scanButton.closest("form");
        if (!form) throw new Error("LAN discovery form was not rendered");
        fireEvent.submit(form);

        expect(await screen.findByText(title)).toBeTruthy();
        expect(screen.getByText(message)).toBeTruthy();
        expect(scanButton.disabled).toBe(false);
    });
});