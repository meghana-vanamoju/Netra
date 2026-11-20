import { useCallback, useEffect, useState } from "react";
import {
  applyNetworkControl,
  createNetworkControlPlan,
  getConnectedDevices,
  getNetworkTopologyStatus,
  verifyNetworkControl,
} from "../api";
import type {
  ApiError,
  ConnectedDevice,
  ConnectedDevicesResponse,
  NetworkControlAction,
  NetworkControlPlanResponse,
  NetworkTopologyStatus,
  ResourceState,
} from "../types";
import { ErrorMessage, Icon, LoadingValue } from "./ui";

type PendingAction = {
  device: ConnectedDevice;
  action: NetworkControlAction;
};

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function displayDate(value: string | null) {
  if (!value) return "Not observed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function accessLabel(device: ConnectedDevice) {
  switch (device.internet_access) {
    case "blocked":
      return "Firewall rules verified";
    case "allowed":
      return "No Netra block rules";
    case "blocked_pending_verification":
      return "Firewall state unverified";
    case "reconciliation_required":
      return "Identity changed — review required";
    case "enforcement_error":
      return "Enforcement error";
    case "pending":
      return "Pending";
    case "identity_validation_required":
      return "Identity validation required";
    default:
      return "Unknown";
  }
}

function statusLabel(value: string) {
  return value.replace(/_/g, " ");
}

export function ConnectedDevicesPage() {
  const [network, setNetwork] = useState<ResourceState<NetworkTopologyStatus>>({
    status: "loading",
  });
  const [devices, setDevices] = useState<
    ResourceState<ConnectedDevicesResponse>
  >({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [plan, setPlan] = useState<
    ResourceState<NetworkControlPlanResponse>
  >({ status: "loading" });
  const [dialogError, setDialogError] = useState<ApiError | null>(null);
  const [approver, setApprover] = useState("");
  const [applying, setApplying] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    const [networkResult, deviceResult] = await Promise.allSettled([
      getNetworkTopologyStatus(),
      getConnectedDevices(),
    ]);
    setNetwork(
      networkResult.status === "fulfilled"
        ? { status: "ready", data: networkResult.value }
        : { status: "error", error: toApiError(networkResult.reason) },
    );
    setDevices(
      deviceResult.status === "fulfilled"
        ? { status: "ready", data: deviceResult.value }
        : { status: "error", error: toApiError(deviceResult.reason) },
    );
    setRefreshing(false);
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      if (!active) return;
      await loadData();
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 10_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [loadData]);

  useEffect(() => {
    if (!pendingAction) return;
    let active = true;
    setPlan({ status: "loading" });
    setDialogError(null);
    setApprover("");
    const deviceId = pendingAction.device.device_id;
    if (deviceId === null) {
      setPlan({
        status: "error",
        error: new Error("A validated device identity is required."),
      });
      return () => {
        active = false;
      };
    }
    void createNetworkControlPlan(
      deviceId,
      pendingAction.action,
    ).then(
      (result) => {
        if (active) setPlan({ status: "ready", data: result });
      },
      (error) => {
        if (active) {
          setPlan({ status: "error", error: toApiError(error) });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [pendingAction]);

  const openAction = (
    device: ConnectedDevice,
    action: NetworkControlAction,
  ) => {
    setNotice(null);
    setPendingAction({ device, action });
  };

  const closeDialog = () => {
    if (applying) return;
    setPendingAction(null);
    setDialogError(null);
  };

  const confirmAction = async () => {
    if (
      !pendingAction ||
      plan.status !== "ready" ||
      !plan.data.plan.apply_allowed ||
      !approver.trim()
    ) {
      return;
    }
    const deviceId = pendingAction.device.device_id;
    if (deviceId === null) return;
    setApplying(true);
    setDialogError(null);
    try {
      const applied = await applyNetworkControl(
        deviceId,
        plan.data.plan_id,
        pendingAction.action,
        approver.trim(),
      );
      if (!applied.verified) {
        throw new Error(
          "The backend did not verify the requested internet-access change.",
        );
      }
      const verification = await verifyNetworkControl(deviceId);
      const expected =
        pendingAction.action === "block_internet" ? "blocked" : "allowed";
      if (!verification.verified || verification.internet_access !== expected) {
        throw new Error(
          "The final firewall verification did not match the requested state.",
        );
      }

      setDevices((current) => {
        if (current.status !== "ready") return current;
        return {
          status: "ready",
          data: {
            ...current.data,
            devices: current.data.devices.map((device) =>
              device.device_id === deviceId
                ? {
                  ...device,
                  internet_access: expected,
                  enforcement_status:
                    pendingAction.action === "block_internet"
                      ? "applied"
                      : "reverted",
                  verification_status: "rules_verified",
                }
                : device,
            ),
          },
        };
      });
      setNotice(
        expected === "blocked"
          ? `Firewall rules were verified for ${pendingAction.device.name}; physical connectivity was not tested.`
          : `Netra firewall restrictions were removed for ${pendingAction.device.name}; physical connectivity was not tested.`,
      );
      setPendingAction(null);
    } catch (error) {
      setDialogError(toApiError(error));
    } finally {
      setApplying(false);
      void loadData();
    }
  };

  const connectedCount =
    devices.status === "ready"
      ? devices.data.connected_device_count
      : network.status === "ready"
        ? network.data.connected_device_count
        : 0;
  const rows = devices.status === "ready" ? devices.data.devices : [];
  const actionName =
    pendingAction?.action === "block_internet" ? "Block Internet" : "Restore Internet";

  return (
    <section className="connected-devices-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            HOTSPOT DEVICE CONTROL
          </div>
          <h1>Connected <span>Devices.</span></h1>
          <p className="page-description">
            Manage internet access for individual clients connected to this laptop’s Wi-Fi hotspot.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => void loadData()}
          disabled={refreshing}
        >
          <Icon name="refresh" size={16} />
          <span>{refreshing ? "Refreshing…" : "Refresh"}</span>
        </button>
      </div>

      {notice && (
        <div className="network-control-notice" role="status">
          <Icon name="check" size={17} />
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss message">
            ×
          </button>
        </div>
      )}

      {network.status === "error" ? (
        <div className="panel network-control-error">
          <ErrorMessage error={network.error} />
        </div>
      ) : network.status === "loading" ? (
        <div className="panel network-control-loading" role="status">
          <LoadingValue />
          <span>Detecting the active uplink and hotspot…</span>
        </div>
      ) : (
        <>
          <div className="network-status-grid" aria-label="Network status">
            <article className="panel network-status-card">
              <span className="metric-label">UPLINK ROUTE</span>
              <strong>
                {network.data.uplink.connected
                  ? "Default route active"
                  : "No default route detected"}
              </strong>
              <span>
                {network.data.uplink.connection_type || "Unknown"} ·{" "}
                {network.data.uplink.interface || "Interface unavailable"}
              </span>
              <small>
                IP: {network.data.uplink.ip_address || "Not detected"}
                {network.data.uplink.gateway
                  ? ` · Gateway: ${network.data.uplink.gateway}`
                  : ""}
              </small>
              <small>Default-route detection does not test Internet reachability.</small>
            </article>
            <article className="panel network-status-card">
              <span className="metric-label">WI-FI HOTSPOT</span>
              <strong>{network.data.hotspot.active ? "Active" : "Unavailable"}</strong>
              <span>
                {network.data.hotspot.interface || "Interface unavailable"} ·{" "}
                {network.data.hotspot.ip_address || "IP unavailable"}
              </span>
              <small>
                Subnet: {network.data.hotspot.subnet || "Not detected"}
              </small>
            </article>
            <article className="panel network-status-card">
              <span className="metric-label">CONNECTED DEVICES</span>
              <strong>{connectedCount}</strong>
              <span>Current Wi-Fi associations</span>
              <small>Refreshed automatically every 10 seconds</small>
            </article>
            <article className="panel network-status-card">
              <span className="metric-label">NETWORK ENFORCEMENT</span>
              <strong className={`network-enforcement-state ${network.data.enforcement.status}`}>
                {network.data.enforcement.configuration_ready
                  ? "Configuration ready"
                  : statusLabel(network.data.enforcement.status)}
              </strong>
              <span>
                {network.data.enforcement.interface || "Hotspot interface not verified"}
              </span>
              <small>
                {network.data.enforcement.apply_permitted
                  ? "Restricted helper authorized; each change still requires confirmation"
                  : "Changes are unavailable until enforcement and the helper are deliberately enabled"}
              </small>
              <small>
                Helper: {statusLabel(network.data.enforcement.helper_status)} · nft in helper: {network.data.enforcement.nftables_binary_available ? "available" : "unavailable"}
              </small>
              <small>
                Backend CAP_NET_ADMIN: {statusLabel(network.data.enforcement.backend_cap_net_admin)} · {statusLabel(network.data.enforcement.privilege_model)}
              </small>
              <small>Physical connectivity: not tested</small>
            </article>
          </div>

          {(network.data.warnings.length > 0 ||
            (devices.status === "ready" && devices.data.warnings.length > 0)) && (
              <div className="network-control-warning" role="status">
                <strong>Discovery notes</strong>
                <ul>
                  {[...new Set([
                    ...network.data.warnings,
                    ...(devices.status === "ready" ? devices.data.warnings : []),
                  ])].map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              </div>
            )}

          <div className="panel connected-device-panel">
            <div className="panel-header connected-device-header">
              <div>
                <div className="panel-kicker">LIVE HOTSPOT INVENTORY</div>
                <h2>Connected Devices</h2>
              </div>
              <span className="connected-device-count">
                {connectedCount} connected
              </span>
            </div>

            {devices.status === "loading" ? (
              <div className="network-control-loading" role="status">
                <LoadingValue />
                <span>Discovering hotspot clients…</span>
              </div>
            ) : devices.status === "error" ? (
              <div className="network-control-error">
                <ErrorMessage error={devices.error} />
              </div>
            ) : rows.length === 0 ? (
              <div className="empty-state connected-device-empty">
                <span className="empty-icon"><Icon name="devices" size={20} /></span>
                <strong>No hotspot clients detected</strong>
                <span>
                  Connected clients are detected from Wi-Fi station data and correlated with DHCP leases or neighbor entries.
                </span>
              </div>
            ) : (
              <div className="connected-device-table-wrap">
                <table className="device-table connected-device-table">
                  <thead>
                    <tr>
                      <th>Device</th>
                      <th>IP address</th>
                      <th>MAC address</th>
                      <th>Wi-Fi connection</th>
                      <th>Netra firewall state</th>
                      <th>Last seen</th>
                      <th>Block Internet</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((device) => {
                      const blocked = device.internet_access === "blocked";
                      const knownAccess =
                        device.internet_access === "allowed" || blocked;
                      const canControl =
                        device.connection_status === "connected" &&
                        device.identity_status === "validated" &&
                        device.device_id !== null &&
                        knownAccess &&
                        network.data.enforcement.status !== "interface_mismatch";
                      return (
                        <tr key={device.device_id ?? `${device.mac_address}-${device.ip_address}`}>
                          <td>
                            <span className="device-name-cell">
                              <span className="device-avatar"><Icon name="devices" size={16} /></span>
                              <span>
                                <strong>{device.name}</strong>
                                <small>
                                  {device.device_id === null
                                    ? "Identity validation required"
                                    : `Device #${device.device_id}`}
                                </small>
                              </span>
                            </span>
                          </td>
                          <td className="ip-address">{device.ip_address || "Not assigned"}</td>
                          <td className="ip-address">{device.mac_address || "Not reported"}</td>
                          <td>
                            <span className={`device-connection-state ${device.connection_status}`}>
                              {device.connection_status === "connected" ? "Connected" : "Disconnected"}
                            </span>
                          </td>
                          <td>
                            <span className={`device-access-state ${device.internet_access}`}>
                              {accessLabel(device)}
                            </span>
                            {Boolean(device.enforcement_error) && (
                              <small className="device-access-error">
                                Enforcement state needs attention.
                              </small>
                            )}
                          </td>
                          <td className="last-seen">{displayDate(device.last_seen)}</td>
                          <td>
                            <button
                              className={`device-access-switch${blocked ? " is-blocked" : ""}`}
                              type="button"
                              role="switch"
                              aria-checked={blocked}
                              aria-label={`${blocked ? "Remove firewall restrictions for" : "Install firewall restrictions for"} ${device.name}`}
                              disabled={!canControl}
                              onClick={() =>
                                openAction(
                                  device,
                                  blocked ? "restore_internet" : "block_internet",
                                )
                              }
                            >
                              <span />
                              <span>{blocked ? "Rules verified" : "No rules"}</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <p className="connected-device-safety-note">
            A changed or randomized MAC address may appear as a new device. Netra does not disconnect clients from Wi-Fi. Firewall-rule verification does not test Internet connectivity from the phone; physical confirmation is not available in this dashboard.
          </p>
        </>
      )}

      {pendingAction && (
        <div className="network-control-dialog-backdrop">
          <section
            className="network-control-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="network-control-dialog-title"
          >
            <div className="dialog-header">
              <div>
                <div className="panel-kicker">EXPLICIT NETWORK CHANGE</div>
                <h2 id="network-control-dialog-title">{actionName}?</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={closeDialog}
                aria-label="Close confirmation"
                disabled={applying}
              >
                ×
              </button>
            </div>
            <p className="network-control-confirm-copy">
              {pendingAction.action === "block_internet"
                ? `Netra will install forwarding rules for ${pendingAction.device.name}. The dashboard cannot confirm the phone's Internet connectivity; other devices are not selected.`
                : `Netra's forwarding rules will be removed for ${pendingAction.device.name}. The dashboard cannot confirm the phone's Internet connectivity.`}
            </p>
            <div className="network-control-target">
              <span>Device</span><strong>{pendingAction.device.name}</strong>
              <span>IP</span><strong>{pendingAction.device.ip_address || "Not available"}</strong>
              <span>MAC</span><strong>{pendingAction.device.mac_address || "Not available"}</strong>
            </div>

            {plan.status === "loading" ? (
              <div className="network-control-loading" role="status">
                <LoadingValue /><span>Building a no-change dry-run plan…</span>
              </div>
            ) : plan.status === "error" ? (
              <ErrorMessage error={plan.error} />
            ) : (
              <>
                <div className="network-plan-summary">
                  <strong>Dry-run impact</strong>
                  <span>{plan.data.impact.scope}</span>
                  <span>
                    {plan.data.impact.network_change
                      ? "This plan changes network state."
                      : "No network state has changed yet."}
                  </span>
                </div>
                {plan.data.plan.warnings.length > 0 && (
                  <div className="network-control-warning">
                    <strong>Plan warnings</strong>
                    <ul>{plan.data.plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                  </div>
                )}
                {!plan.data.plan.apply_allowed && (
                  <div className="network-control-warning">
                    <strong>Apply is disabled</strong>
                    <ul>
                      {plan.data.plan.apply_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                    </ul>
                  </div>
                )}
                <label className="network-control-approver">
                  Confirming user
                  <input
                    value={approver}
                    onChange={(event) => setApprover(event.target.value)}
                    maxLength={128}
                    autoComplete="name"
                    placeholder="Enter your name"
                    disabled={applying}
                  />
                </label>
              </>
            )}

            {dialogError && <ErrorMessage error={dialogError} />}
            <div className="network-control-dialog-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={closeDialog}
                disabled={applying}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void confirmAction()}
                disabled={
                  applying ||
                  plan.status !== "ready" ||
                  !plan.data.plan.apply_allowed ||
                  !approver.trim()
                }
              >
                {applying ? "Applying and verifying…" : `Confirm ${actionName}`}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
