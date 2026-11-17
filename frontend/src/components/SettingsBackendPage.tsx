import { useCallback, useEffect, useState } from "react";
import {
  getBackendCapabilities,
  getDatabaseHealth,
  getHealth,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import type {
  ApiError,
  BackendCapabilities,
  HealthResponse,
  ResourceState,
} from "../types";

type SettingsStatus = {
  backend: ResourceState<HealthResponse>;
  database: ResourceState<{ status: string }>;
  capabilities: ResourceState<BackendCapabilities>;
};

const initialState: SettingsStatus = {
  backend: { status: "loading" },
  database: { status: "loading" },
  capabilities: { status: "loading" },
};

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function statusStyle(ok: boolean | null) {
  if (ok === true) {
    return "settings-status-good";
  }
  if (ok === false) {
    return "settings-status-unavailable";
  }
  return "settings-status-unknown";
}

function StatusValue({
  state,
  value,
  ok,
  unavailable = "Unavailable",
}: {
  state: ResourceState<unknown>;
  value?: string;
  ok?: boolean | null;
  unavailable?: string;
}) {
  if (state.status === "loading") {
    return <span className="settings-loading"><LoadingValue /> Checking…</span>;
  }
  if (state.status === "error") {
    return <ErrorMessage error={state.error} />;
  }
  return (
    <span className={`settings-status ${statusStyle(ok ?? null)}`}>
      {value ?? unavailable}
    </span>
  );
}

type Capability = {
  name: string;
  status: "available" | "limited" | "unsupported";
  summary: string;
  detail: string;
};

const capabilities: Capability[] = [
  {
    name: "LAN discovery",
    status: "available",
    summary: "Explicit scan endpoint available",
    detail: "Runs only on request, synchronously, from the backend host's local network context. It has no progress or durable scan history.",
  },
  {
    name: "DNS analytics",
    status: "available",
    summary: "Stored-event analytics available",
    detail: "Summary, domain, and device aggregates read persisted DNS events. The analytics API does not itself collect traffic.",
  },
  {
    name: "Policy planning",
    status: "limited",
    summary: "Plan and dry-run endpoints available",
    detail: "Planning saves proposed policies and dry-run saves a plan record. Neither action applies configuration.",
  },
  {
    name: "Enforcement",
    status: "unsupported",
    summary: "Policy application is not implemented",
    detail: "A configured DNS backend is only a configuration signal. The adapter does not apply policies or confirm traffic protection.",
  },
  {
    name: "Verification",
    status: "unsupported",
    summary: "Currently returns not_verified",
    detail: "The verification endpoint does not confirm policy effectiveness or active traffic protection.",
  },
  {
    name: "Snapshots",
    status: "limited",
    summary: "Read and inspection supported",
    detail: "Snapshot records can be listed and inspected. Snapshot rollback is not implemented.",
  },
  {
    name: "Recovery",
    status: "unsupported",
    summary: "Status only; recovery action unavailable",
    detail: "The recovery status endpoint returns fixed values; it does not perform or verify restoration.",
  },
];

function capabilityStatusText(status: Capability["status"]) {
  switch (status) {
    case "available":
      return "API AVAILABLE";
    case "limited":
      return "LIMITED";
    case "unsupported":
      return "UNSUPPORTED";
  }
}

export function SettingsBackendPage() {
  const [data, setData] = useState<SettingsStatus>(initialState);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setData({
      backend: { status: "loading" },
      database: { status: "loading" },
      capabilities: { status: "loading" },
    });

    const [backend, database, capabilityData] = await Promise.allSettled([
      getHealth(),
      getDatabaseHealth(),
      getBackendCapabilities(),
    ]);

    setData({
      backend:
        backend.status === "fulfilled"
          ? { status: "ready", data: backend.value }
          : { status: "error", error: toApiError(backend.reason) },
      database:
        database.status === "fulfilled"
          ? { status: "ready", data: database.value }
          : { status: "error", error: toApiError(database.reason) },
      capabilities:
        capabilityData.status === "fulfilled"
          ? { status: "ready", data: capabilityData.value }
          : { status: "error", error: toApiError(capabilityData.reason) },
    });
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const backendOk =
    data.backend.status === "ready" ? data.backend.data.status === "ok" : null;
  const databaseOk =
    data.database.status === "ready" ? data.database.data.status === "ok" : null;
  const dnsBackendConfigured =
    data.capabilities.status === "ready"
      ? data.capabilities.data.available
      : null;

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> SYSTEM CONFIGURATION</div>
          <h1>Settings <span>&amp; backend.</span></h1>
          <p className="page-description">
            Read-only service health, backend configuration, and API capability information.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          aria-label={refreshing ? "Refreshing backend status" : "Refresh status"}
          onClick={() => void refresh()}
          disabled={refreshing}
        >
          <Icon name="refresh" size={16} />
          <span>{refreshing ? "Refreshing…" : "Refresh status"}</span>
        </button>
      </div>

      <div className="settings-safety-note">
        <Icon name="lock" size={16} />
        <span>
          This page only reads backend status. It does not expose settings changes or indicate that network traffic is protected.
        </span>
      </div>

      <section className="settings-overview-grid" aria-label="Backend health and configuration">
        <article className="panel settings-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">SERVICE HEALTH</div>
              <h2>Backend service</h2>
            </div>
            <span className={`metric-icon ${backendOk ? "green" : "amber"}`}>
              <Icon name="router" size={17} />
            </span>
          </div>
          <StatusValue
            state={data.backend}
            ok={backendOk}
            value={
              data.backend.status === "ready"
                ? data.backend.data.status === "ok"
                  ? "Healthy"
                  : `Reported: ${data.backend.data.status || "unknown"}`
                : undefined
            }
            unavailable="Unavailable"
          />
          {data.backend.status === "ready" && (
            <dl className="settings-data-list">
              <div><dt>Service</dt><dd>{data.backend.data.service || "Not reported"}</dd></div>
              <div><dt>Version</dt><dd>{data.backend.data.version || "Not reported"}</dd></div>
            </dl>
          )}
          {data.backend.status === "ready" && backendOk && (
            <p className="settings-detail">
              Service health confirms the API responded. It does not imply active DNS filtering.
            </p>
          )}
        </article>

        <article className="panel settings-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">DATA STORE</div>
              <h2>Database health</h2>
            </div>
            <span className={`metric-icon ${databaseOk ? "green" : "amber"}`}>
              <Icon name="lock" size={17} />
            </span>
          </div>
          <StatusValue
            state={data.database}
            ok={databaseOk}
            value={
              data.database.status === "ready"
                ? data.database.data.status === "ok"
                  ? "Healthy"
                  : `Reported: ${data.database.data.status || "unknown"}`
                : undefined
            }
            unavailable="Unavailable"
          />
          <p className="settings-detail">
            Database health is reported by a read-only connectivity check.
          </p>
        </article>

        <article className="panel settings-panel settings-config-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">DNS CONFIGURATION</div>
              <h2>Configured backend</h2>
            </div>
            <span className={`metric-icon ${dnsBackendConfigured ? "blue" : "amber"}`}>
              <Icon name="router" size={17} />
            </span>
          </div>
          {data.capabilities.status === "loading" ? (
            <StatusValue state={data.capabilities} />
          ) : data.capabilities.status === "error" ? (
            <ErrorMessage error={data.capabilities.error} />
          ) : (
            <>
              <div className="settings-config-row">
                <span className={`settings-status ${statusStyle(dnsBackendConfigured)}`}>
                  {dnsBackendConfigured
                    ? "CONFIGURED"
                    : "NO BACKEND CONFIGURED"}
                </span>
                <strong>
                  {data.capabilities.data.configured_backend || "Not configured"}
                </strong>
              </div>
              <dl className="settings-data-list">
                <div><dt>Capability status</dt><dd>{data.capabilities.data.status || "Not reported"}</dd></div>
              </dl>
              <p className="settings-detail">
                The backend name is read from <code>NETRA_DNS_BACKEND</code> on the server. It must be configured outside this dashboard. Configuration does not mean policy enforcement is implemented.
              </p>
            </>
          )}
        </article>
      </section>

      <section className="panel settings-capabilities-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">BACKEND API SURFACE</div>
            <h2>Capabilities &amp; limitations</h2>
          </div>
          <span className="read-only-tag">INFORMATION ONLY</span>
        </div>
        <p className="settings-detail settings-capabilities-intro">
          These labels describe implemented backend API behavior, not capabilities inferred from the frontend or from current network protection.
        </p>
        <div className="settings-capabilities-grid">
          {capabilities.map((capability) => (
            <article className="settings-capability-card" key={capability.name}>
              <div className="settings-capability-heading">
                <h3>{capability.name}</h3>
                <span className={`settings-status settings-status-${capability.status}`}>
                  {capabilityStatusText(capability.status)}
                </span>
              </div>
              <strong>{capability.summary}</strong>
              <p>{capability.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <p className="settings-limitation">
        No configuration values are editable here. API availability, database health, and a configured DNS backend are separate facts; none confirms active protection.
      </p>
    </section>
  );
}
