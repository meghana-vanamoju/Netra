import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
    getDevices,
    getDiscoveryResults,
    getLocalNetworkInfo,
    getRouterCapabilities,
    getRouterDevices,
    runDiscovery,
    testRouter,
} from "../api";
import { ErrorMessage, Icon } from "./ui";
import { LocalizedTree } from "../localization";
import type {
    ApiError,
    Device,
    DiscoveryResponse,
    DiscoveryResult,
    LocalNetworkInfo,
    ResourceState,
    RouterCapabilities,
    RouterDevicesResponse,
    RouterTestResponse,
} from "../types";

function toApiError(error: unknown): ApiError {
    return error instanceof Error
        ? error
        : new Error(`Unexpected API error: ${String(error)}`);
}

function discoveryErrorTitle(error: ApiError) {
    if (error.status === 0) {
        return /timed out/i.test(error.message)
            ? "Discovery request timed out"
            : "Backend connection failed";
    }
    if (error.status === 408 || error.status === 504) {
        return "Discovery request timed out";
    }
    if (typeof error.status === "number" && error.status >= 500) {
        return "Discovery service error";
    }
    return "LAN discovery failed";
}

function isPrivateIPv4(value: string) {
    const parts = value.split(".").map(Number);
    if (
        parts.length !== 4 ||
        parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
    ) {
        return false;
    }
    return (
        parts[0] === 10 ||
        (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
        (parts[0] === 192 && parts[1] === 168)
    );
}

function validateSubnet(value: string) {
    const [address, prefixText, extra] = value.split("/");
    const prefix = Number(prefixText);
    return (
        !extra &&
        prefixText !== undefined &&
        Number.isInteger(prefix) &&
        prefix >= 16 &&
        prefix <= 32 &&
        isPrivateIPv4(address)
    );
}

export function DiscoveryPage() {
    const [network, setNetwork] = useState<ResourceState<LocalNetworkInfo>>({
        status: "loading",
    });
    const [routerIp, setRouterIp] = useState("");
    const [subnet, setSubnet] = useState("");
    const [routerBusy, setRouterBusy] = useState(false);
    const [discoveryBusy, setDiscoveryBusy] = useState(false);
    const [scanElapsedSeconds, setScanElapsedSeconds] = useState(0);
    const discoveryLock = useRef(false);
    const [routerTest, setRouterTest] = useState<RouterTestResponse | null>(null);
    const [capabilities, setCapabilities] =
        useState<RouterCapabilities | null>(null);
    const [routerDevices, setRouterDevices] =
        useState<RouterDevicesResponse | null>(null);
    const [routerError, setRouterError] = useState<ApiError | null>(null);
    const [discoveryError, setDiscoveryError] = useState<ApiError | null>(null);
    const [scanResponse, setScanResponse] =
        useState<DiscoveryResponse | null>(null);
    const [results, setResults] =
        useState<ResourceState<DiscoveryResult[]>>({ status: "loading" });
    const [inventory, setInventory] =
        useState<ResourceState<Device[]>>({ status: "loading" });
    const [lastDiscovery, setLastDiscovery] = useState<string | null>(null);

    useEffect(() => {
        if (!discoveryBusy) return;
        const startedAt = Date.now();
        const updateElapsed = () => {
            setScanElapsedSeconds((Date.now() - startedAt) / 1000);
        };
        const timer = window.setInterval(updateElapsed, 250);
        return () => window.clearInterval(timer);
    }, [discoveryBusy]);

    useEffect(() => {
        let active = true;
        getLocalNetworkInfo().then(
            (info) => {
                if (!active) return;
                setNetwork({ status: "ready", data: info });
                setRouterIp(info.gateway ?? "");
                setSubnet(info.subnet ?? "");
            },
            (error) => {
                if (active) setNetwork({ status: "error", error: toApiError(error) });
            },
        );
        return () => {
            active = false;
        };
    }, []);

    const refreshInventory = async () => {
        const [resultResponse, deviceResponse] = await Promise.allSettled([
            getDiscoveryResults(),
            getDevices(),
        ]);
        setResults(
            resultResponse.status === "fulfilled"
                ? { status: "ready", data: resultResponse.value }
                : { status: "error", error: toApiError(resultResponse.reason) },
        );
        setInventory(
            deviceResponse.status === "fulfilled"
                ? { status: "ready", data: deviceResponse.value }
                : { status: "error", error: toApiError(deviceResponse.reason) },
        );
        if (deviceResponse.status === "fulfilled") {
            window.dispatchEvent(new Event("netra:inventory-updated"));
        }
    };

    useEffect(() => {
        void refreshInventory();
    }, []);

    const detectRouter = async (event?: FormEvent<HTMLFormElement>) => {
        event?.preventDefault();
        const ip = routerIp.trim();
        setRouterError(null);
        setRouterTest(null);
        setCapabilities(null);
        setRouterDevices(null);
        if (!isPrivateIPv4(ip)) {
            setRouterError(new Error("Enter a private IPv4 address such as 192.168.88.1."));
            return;
        }
        setRouterBusy(true);
        try {
            const [test, report] = await Promise.all([
                testRouter(ip),
                getRouterCapabilities(ip),
            ]);
            setRouterTest(test);
            setCapabilities(report);
            if (report.adguard_home_configured) {
                const response = await getRouterDevices(ip);
                setRouterDevices(response);
                setLastDiscovery(new Date().toISOString());
                await refreshInventory();
            }
        } catch (error) {
            setRouterError(toApiError(error));
        } finally {
            setRouterBusy(false);
        }
    };

    const retrieveRouterInventory = async () => {
        const ip = routerIp.trim();
        setRouterError(null);
        if (!isPrivateIPv4(ip)) {
            setRouterError(new Error("Enter a private IPv4 address before retrieving router devices."));
            return;
        }
        setRouterBusy(true);
        try {
            const response = await getRouterDevices(ip);
            setRouterDevices(response);
            setLastDiscovery(new Date().toISOString());
            await refreshInventory();
        } catch (error) {
            setRouterError(toApiError(error));
        } finally {
            setRouterBusy(false);
        }
    };

    const runLanDiscovery = async () => {
        if (discoveryLock.current) return;
        const requestedSubnet = subnet.trim();
        setDiscoveryError(null);
        setScanResponse(null);
        if (!validateSubnet(requestedSubnet)) {
            setDiscoveryError(
                new Error("Enter a private IPv4 subnet in CIDR form, no larger than /16."),
            );
            return;
        }
        discoveryLock.current = true;
        setScanElapsedSeconds(0);
        setDiscoveryBusy(true);
        setResults({ status: "loading" });
        try {
            const response = await runDiscovery(requestedSubnet);
            setScanResponse(response);
            setLastDiscovery(new Date().toISOString());
            await refreshInventory();
        } catch (error) {
            setDiscoveryError(toApiError(error));
            setResults({ status: "error", error: toApiError(error) });
        } finally {
            discoveryLock.current = false;
            setDiscoveryBusy(false);
        }
    };

    const runUnifiedDiscovery = async () => {
        setRouterError(null);
        if (isPrivateIPv4(routerIp.trim())) {
            setRouterBusy(true);
            try {
                const response = await getRouterDevices(routerIp.trim());
                setRouterDevices(response);
            } catch (error) {
                setRouterDevices(null);
                setRouterError(toApiError(error));
            } finally {
                setRouterBusy(false);
            }
        }
        await runLanDiscovery();
    };

    const shownDevices: DiscoveryResult[] =
        results.status === "ready"
            ? [
                ...results.data,
                ...(inventory.status === "ready"
                    ? inventory.data
                        .filter((stored) =>
                            !results.data.some(
                                (observed) =>
                                    (stored.mac_address &&
                                        stored.mac_address.toUpperCase() ===
                                        observed.mac_address?.toUpperCase()) ||
                                    stored.ip_address === observed.ip_address,
                            ),
                        )
                        .map((stored) => ({
                            ip_address: stored.ip_address,
                            mac_address: stored.mac_address,
                            hostname: stored.hostname,
                            discovery_source: stored.discovery_source ?? "previously-seen",
                            sources: Array.isArray(stored.metadata?.sources)
                                ? stored.metadata.sources.filter(
                                    (source): source is string => typeof source === "string",
                                )
                                : [],
                        }))
                    : []),
            ]
            : [];

    const formatTimestamp = (value: string | undefined) => {
        if (!value) return "Unknown";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString();
    };

    const managementStatus = routerDevices
        ? routerDevices.status === "available"
            ? "AdGuard Home API responding"
            : routerDevices.status === "authentication_required"
                ? "Authentication required"
                : routerDevices.status === "unsupported"
                    ? "Not detected/configured"
                    : `AdGuard Home ${routerDevices.status.replace(/_/g, " ")}`
        : capabilities?.adguard_home_configured
            ? "AdGuard Home configured"
            : "Not detected/configured";
    const authenticationStatus = routerDevices
        ? routerDevices.authentication_required === true
            ? "Required"
            : routerDevices.authentication_required === false
                ? "Not required"
                : routerDevices.authentication_required === "configured"
                    ? "Credentials configured"
                    : "Unknown"
        : capabilities?.adguard_home_configured
            ? "Checked during retrieval"
            : "Unknown";

    return (
        <LocalizedTree>
            <section className="discovery-page">
                <div className="page-heading">
                    <div>
                        <div className="eyebrow"><span className="eyebrow-line" /> LOCAL NETWORK</div>
                        <h1>LAN <span>discovery.</span></h1>
                        <p className="page-description">
                            Check router support, retrieve available DHCP leases, and combine them with local network observations.
                        </p>
                    </div>
                </div>

                <div className="discovery-safety">
                    <span className="safety-icon"><Icon name="lock" size={18} /></span>
                    <div>
                        <strong>Read-only, user-initiated discovery</strong>
                        <p>
                            Router configuration is never changed. LAN fallback uses the Netra host's local neighbor table and bounded probes; network isolation or missing permissions can hide devices.
                        </p>
                    </div>
                </div>

                <section className="panel discovery-form-panel" aria-labelledby="router-form-title">
                    <div className="panel-header">
                        <div>
                            <div className="panel-kicker">ROUTER CONNECTION</div>
                            <h2 id="router-form-title">Detect router support</h2>
                        </div>
                        <span className="read-only-tag"><Icon name="lock" size={13} /> READ-ONLY</span>
                    </div>
                    <div className="network-context">
                        {network.status === "loading" ? "Detecting active network…" : network.status === "ready" ? (
                            <span>
                                Active: <b data-no-translate="true">{network.data.interface || "unknown interface"}</b>
                                {network.data.ip_address && <> · <b data-no-translate="true">{network.data.ip_address}</b></>}
                                {network.data.gateway && <> · gateway <b data-no-translate="true">{network.data.gateway}</b></>}
                            </span>
                        ) : "Active network could not be detected; enter the gateway and subnet manually."}
                    </div>
                    {network.status === "error" && <ErrorMessage error={network.error} />}
                    <form className="discovery-form" onSubmit={(event) => void detectRouter(event)}>
                        <label className="search-control subnet-control">
                            <span>Router / gateway IPv4 address</span>
                            <input
                                type="text"
                                value={routerIp}
                                onChange={(event) => setRouterIp(event.target.value)}
                                placeholder="192.168.88.1"
                                autoComplete="off"
                                spellCheck={false}
                                required
                                disabled={routerBusy || discoveryBusy}
                            />
                        </label>
                        <button className="primary-button" type="submit" disabled={routerBusy || discoveryBusy}>
                            <Icon name="router" size={17} />
                            {routerBusy ? "Checking…" : "Detect router"}
                        </button>
                    </form>
                    {routerError && <ErrorMessage error={routerError} />}
                    {routerTest && capabilities && (
                        <div className="router-report" role="status">
                            <div className={`router-report-status${routerTest.network_reachable ? " is-online" : ""}`}>
                                <span className="status-dot" />
                                {routerTest.network_reachable ? "Present on local network" : "No local neighbor evidence"}
                            </div>
                            <div><span>Management API</span><strong>{managementStatus}</strong></div>
                            <div><span>Connected devices</span><strong>{capabilities.connected_devices}</strong></div>
                            <div><span>DHCP leases</span><strong>{capabilities.dhcp_leases}</strong></div>
                            <div><span>Authentication</span><strong>{authenticationStatus}</strong></div>
                            <p>
                                ARP/neighbor presence confirms only local network reachability. It does not prove that router management is supported.
                            </p>
                        </div>
                    )}
                    {capabilities?.adguard_home_configured && (
                        <button className="secondary-button router-retrieve-button" type="button" disabled={routerBusy || discoveryBusy} onClick={() => void retrieveRouterInventory()}>
                            {routerBusy ? "Retrieving…" : "Retrieve connected devices"}
                        </button>
                    )}
                    {routerDevices && (
                        <div className={`router-device-status status-${routerDevices.status}`} role="status">
                            {routerDevices.status === "available"
                                ? `${routerDevices.devices.length} router-reported device${routerDevices.devices.length === 1 ? "" : "s"}.`
                                : routerDevices.status === "unsupported"
                                    ? "This router has no configured supported inventory adapter. LAN discovery remains available."
                                    : routerDevices.status === "authentication_required"
                                        ? "AdGuard Home requires authentication. Configure credentials on the backend; they are not entered or returned in this page."
                                        : `Router inventory is ${routerDevices.status.replace(/_/g, " ")}.`}
                        </div>
                    )}
                </section>

                <section className="panel discovery-form-panel" aria-labelledby="lan-form-title">
                    <div className="panel-header">
                        <div>
                            <div className="panel-kicker">LAN FALLBACK</div>
                            <h2 id="lan-form-title">Discover reachable devices</h2>
                        </div>
                        <span className="read-only-tag"><Icon name="pulse" size={13} /> LOCAL NETWORK</span>
                    </div>
                    <form className="discovery-form" onSubmit={(event) => { event.preventDefault(); void runLanDiscovery(); }}>
                        <label className="search-control subnet-control">
                            <span>Authorized private subnet in CIDR notation</span>
                            <input
                                type="text"
                                value={subnet}
                                onChange={(event) => setSubnet(event.target.value)}
                                placeholder="192.168.88.0/24"
                                autoComplete="off"
                                spellCheck={false}
                                required
                                disabled={routerBusy || discoveryBusy}
                            />
                        </label>
                        <button className="secondary-button" type="submit" disabled={network.status === "loading" || routerBusy || discoveryBusy}>
                            {discoveryBusy ? "Discovering…" : network.status === "loading" ? "Detecting network…" : "LAN discovery"}
                        </button>
                        <button className="primary-button" type="button" disabled={network.status === "loading" || routerBusy || discoveryBusy} onClick={() => void runUnifiedDiscovery()}>
                            <Icon name="pulse" size={17} />
                            {routerBusy || discoveryBusy ? "Discovering…" : network.status === "loading" ? "Detecting network…" : "Retrieve router + discover LAN"}
                        </button>
                    </form>
                    <p className="form-help">
                        The scan runs on the machine hosting Netra. It is limited to 64 host probes per run and the selected private subnet; results may be incomplete on isolated Wi-Fi or restricted hosts.
                    </p>
                    {discoveryBusy && (
                        <div className="scan-progress" role="status" aria-live="polite">
                            <span className="scan-spinner" />
                            <strong>Scanning LAN</strong>
                            <span>{scanElapsedSeconds.toFixed(1)}s <span>elapsed</span></span>
                            <span>Up to 64 hosts</span>
                        </div>
                    )}
                    {discoveryError && (
                        <div className="discovery-error" role="alert">
                            <strong>{discoveryErrorTitle(discoveryError)}</strong>
                            <span>{discoveryError.message}</span>
                        </div>
                    )}
                </section>

                <section className="panel scan-results-panel" aria-labelledby="scan-results-title">
                    <div className="panel-header">
                        <div>
                            <div className="panel-kicker">UNIFIED INVENTORY</div>
                            <h2 id="scan-results-title">Discovered devices</h2>
                        </div>
                        {lastDiscovery && <span className="live-tag"><span /> UPDATED {new Date(lastDiscovery).toLocaleTimeString()}</span>}
                    </div>
                    {scanResponse && (
                        <div className="scan-inventory-status" role="status">
                            <strong>{scanResponse.discovered}</strong>
                            <span>{scanResponse.discovered === 1 ? "device discovered" : "devices discovered"}</span>
                            {scanResponse.duration_seconds !== undefined && (
                                <span>{scanResponse.duration_seconds.toFixed(1)}s <span>scan duration</span></span>
                            )}
                            {scanResponse.hosts_responding !== undefined && (
                                <span>{scanResponse.hosts_responding} <span>hosts responding</span></span>
                            )}
                            {scanResponse.probes_attempted !== undefined && (
                                <span>{scanResponse.probes_attempted} <span>probes attempted</span></span>
                            )}
                            {scanResponse.timeout_count !== undefined && (
                                <span>{scanResponse.timeout_count} <span>timed out</span></span>
                            )}
                            {scanResponse.partial_results && <strong>Partial results</strong>}
                        </div>
                    )}
                    {results.status === "loading" ? (
                        <div className="panel-state" role="status">Loading inventory…</div>
                    ) : results.status === "error" ? (
                        discoveryError ? null : <ErrorMessage error={results.error} />
                    ) : results.data.length > 0 ? (
                        <div className="inventory-table-wrap">
                            <table className="device-table discovery-table">
                                <thead><tr><th>IP ADDRESS</th><th>MAC ADDRESS</th><th>HOSTNAME</th><th>VENDOR</th><th>CONNECTION</th><th>STATUS</th><th>LEASE EXPIRES</th><th>SOURCE</th><th>FIRST SEEN</th><th>LAST SEEN</th></tr></thead>
                                <tbody>
                                    {shownDevices.map((device, index) => {
                                        const inventoryDevice = inventory.status === "ready"
                                            ? inventory.data.find((item) => item.mac_address && item.mac_address.toUpperCase() === device.mac_address?.toUpperCase()) ?? inventory.data.find((item) => item.ip_address === device.ip_address)
                                            : undefined;
                                        const metadata = inventoryDevice?.metadata ?? {};
                                        const sources = device.sources ?? [device.discovery_source];
                                        const current = results.status === "ready" && results.data.includes(device);
                                        const hasLan = sources.some((source) => source === "arp" || source?.includes("lan"));
                                        const hasRouter = sources.some((source) => source?.startsWith("router:"));
                                        const status = !current
                                            ? "Previously seen"
                                            : hasLan && hasRouter
                                                ? "LAN + router"
                                                : hasLan
                                                    ? "LAN reachable"
                                                    : hasRouter
                                                        ? "Router-reported"
                                                        : "Observed";
                                        return (
                                            <tr key={`${device.mac_address ?? device.ip_address}-${index}`}>
                                                <td className="ip-address"><span data-no-translate="true">{device.ip_address}</span></td>
                                                <td className="ip-address">{device.mac_address ? <span data-no-translate="true">{device.mac_address}</span> : "Unknown"}</td>
                                                <td>{device.hostname ? <span data-no-translate="true">{device.hostname}</span> : "Unknown"}</td>
                                                <td>{inventoryDevice?.vendor ?? "Unknown"}</td>
                                                <td>{String(metadata.connection_type ?? "Unknown")}</td>
                                                <td>{status}{metadata.online_status && metadata.online_status !== "unknown" ? ` · ${String(metadata.online_status)}` : ""}</td>
                                                <td>{formatTimestamp(typeof metadata.lease_expires === "string" ? metadata.lease_expires : undefined)}</td>
                                                <td>{sources.filter(Boolean).join(", ") || "Unknown"}</td>
                                                <td>{formatTimestamp(inventoryDevice?.first_seen)}</td>
                                                <td>{formatTimestamp(inventoryDevice?.last_seen)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    ) : lastDiscovery ? (
                        <div className="empty-state discovery-empty">
                            <span className="empty-icon"><Icon name="devices" size={20} /></span>
                            <strong>No devices were returned</strong>
                            <span>The discovery request completed with an empty result. Wi-Fi client isolation and host permissions can limit visibility.</span>
                        </div>
                    ) : (
                        <div className="empty-state discovery-empty">
                            <span className="empty-icon"><Icon name="devices" size={20} /></span>
                            <strong>No discovery has run yet</strong>
                            <span>Router management is optional. Run LAN discovery to inspect locally visible neighbors.</span>
                        </div>
                    )}
                </section>
            </section>
        </LocalizedTree>
    );
}