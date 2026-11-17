import { useState } from "react";
import type { FormEvent } from "react";
import {
  getDevices,
  getDiscoveryResults,
  runDiscovery,
} from "../api";
import { ErrorMessage, Icon } from "./ui";
import { LocalizedTree } from "../localization";
import type {
  ApiError,
  Device,
  DiscoveryResponse,
  DiscoveryResult,
  ResourceState,
} from "../types";

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

export function DiscoveryPage() {
  const [subnet, setSubnet] = useState("192.168.1.0/24");
  const [scanning, setScanning] = useState(false);
  const [scanResponse, setScanResponse] = useState<DiscoveryResponse | null>(null);
  const [scanError, setScanError] = useState<ApiError | null>(null);
  const [results, setResults] = useState<ResourceState<DiscoveryResult[]>>({
    status: "loading",
  });
  const [inventory, setInventory] = useState<ResourceState<Device[]>>({
    status: "loading",
  });
  const [hasRun, setHasRun] = useState(false);

  const startDiscovery = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestedSubnet = subnet.trim();
    if (!requestedSubnet || scanning) {
      return;
    }
    const prefixText = requestedSubnet.split("/")[1];
    const prefix = prefixText ? Number(prefixText) : Number.NaN;
    if (Number.isInteger(prefix) && prefix < 16) {
      setScanError(
        new Error(
          "For safety, discovery is limited to private IPv4 subnets no larger than /16.",
        ),
      );
      return;
    }

    setScanning(true);
    setHasRun(true);
    setScanResponse(null);
    setScanError(null);
    setResults({ status: "loading" });

    try {
      const response = await runDiscovery(requestedSubnet);
      setScanResponse(response);

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
    } catch (error) {
      setScanError(toApiError(error));
      setResults({ status: "error", error: toApiError(error) });
      setInventory({ status: "error", error: toApiError(error) });
    } finally {
      setScanning(false);
    }
  };

  return (
    <LocalizedTree>
    <section className="discovery-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> LOCAL NETWORK</div>
          <h1>LAN <span>discovery.</span></h1>
          <p className="page-description">
            Choose a private subnet and start a read-only discovery scan when you are ready.
          </p>
        </div>
      </div>

      <div className="discovery-safety">
        <span className="safety-icon"><Icon name="lock" size={18} /></span>
        <div>
          <strong>Discovery is manual and read-only</strong>
          <p>
            No scan runs when this page opens. The backend probes up to 64 host
            addresses and uses its local ARP table to report devices. It does
            not guarantee every device will respond.
          </p>
        </div>
      </div>

      <section className="panel discovery-form-panel" aria-labelledby="scan-form-title">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">SCAN OPTIONS</div>
            <h2 id="scan-form-title">Discover devices on a subnet</h2>
          </div>
          <span className="read-only-tag"><Icon name="lock" size={13} /> READ-ONLY</span>
        </div>
        <form className="discovery-form" onSubmit={(event) => void startDiscovery(event)}>
          <label className="search-control subnet-control">
            <span>Private subnet in CIDR notation</span>
            <input
              type="text"
              value={subnet}
              onChange={(event) => setSubnet(event.target.value)}
              placeholder="192.168.1.0/24"
              autoComplete="off"
              spellCheck={false}
              required
              disabled={scanning}
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={scanning || !subnet.trim()}
          >
            <Icon name="pulse" size={17} />
            {scanning ? "Scanning…" : "Start discovery"}
          </button>
        </form>
        <p className="form-help">
          Example only — edit this to match your LAN. The backend accepts private
          LAN subnets only. For safety, the UI accepts IPv4 networks up to /16.
          A scan runs on the machine hosting Netra, may take up to a few minutes,
          and may require network permissions.
        </p>
        {scanning && (
          <div className="scan-progress" role="status" aria-live="polite">
            <span className="scan-spinner" />
            <span>
              Waiting for the backend to finish scanning <strong>{subnet.trim()}</strong>.
              No percentage progress is available.
            </span>
          </div>
        )}
        {scanError && <ErrorMessage error={scanError} />}
      </section>

      {scanResponse && (
        <section className="panel scan-results-panel" aria-labelledby="scan-results-title">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">BACKEND RESPONSE</div>
              <h2 id="scan-results-title">Scan completed</h2>
            </div>
            <span className="live-tag"><span /> RESPONSE RECEIVED</span>
          </div>
          <div className="scan-result-summary">
            <div className="scan-count">{scanResponse.discovered}</div>
            <div>
              <strong>devices returned by the discovery endpoint</strong>
              <span>Subnet: {scanResponse.subnet}</span>
            </div>
          </div>
          {scanResponse.discovered === 0 && (
            <p className="scan-caveat">
              The backend returned zero hosts. This does not prove that the subnet
              is empty or that the backend had sufficient permissions to see hosts.
            </p>
          )}
          {results.status === "error" && (
            <div className="result-load-error">
              <span>The scan response was received, but its results list could not be loaded.</span>
              <ErrorMessage error={results.error} />
            </div>
          )}
          {results.status === "loading" ? (
            <div className="panel-state" role="status">Loading returned device details…</div>
          ) : results.status === "ready" && results.data.length > 0 ? (
            <div className="inventory-table-wrap">
              <table className="device-table discovery-table">
                <thead>
                  <tr><th>HOSTNAME</th><th>IP ADDRESS</th><th>MAC ADDRESS</th><th>SOURCE</th></tr>
                </thead>
                <tbody>
                  {results.data.map((device, index) => (
                    <tr key={`${device.ip_address}-${device.mac_address ?? index}`}>
                      <td>{device.hostname ? <span data-no-translate="true">{device.hostname}</span> : "Not resolved"}</td>
                      <td className="ip-address"><span data-no-translate="true">{device.ip_address}</span></td>
                      <td className="ip-address">{device.mac_address ? <span data-no-translate="true">{device.mac_address}</span> : "Not reported"}</td>
                      <td>{device.discovery_source ? <span data-no-translate="true">{device.discovery_source}</span> : "Not reported"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : results.status === "ready" ? (
            <div className="empty-state discovery-empty">
              <span className="empty-icon"><Icon name="devices" size={20} /></span>
              <strong>No hosts were returned by the results endpoint</strong>
              <span>This is the backend's response, not a guarantee that the network has no devices.</span>
            </div>
          ) : null}
          <div className="scan-inventory-status">
            {inventory.status === "ready" ? (
              <span>{inventory.data.length === 200 ? "At least 200 devices" : inventory.data.length} devices currently returned by inventory.</span>
            ) : inventory.status === "error" ? (
              <span>Could not refresh inventory after the scan.</span>
            ) : null}
            {inventory.status === "error" && <ErrorMessage error={inventory.error} />}
          </div>
        </section>
      )}

      {!hasRun && (
        <div className="empty-state discovery-intro">
          <span className="empty-icon"><Icon name="devices" size={21} /></span>
          <strong>No discovery scan has been started</strong>
          <span>Choose a private subnet above. Netra will wait for your explicit action before contacting the discovery endpoint.</span>
        </div>
      )}
    </section>
    </LocalizedTree>
  );
}
