import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { classifyDevice, getClassifications, getDevices } from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import type {
  ApiError,
  Device,
  DeviceClassification,
  ResourceState,
} from "../types";

type SortKey = "hostname" | "ip_address" | "vendor" | "category" | "last_seen";
type SortState = { key: SortKey; direction: "ascending" | "descending" };

const pageSizes = [10, 25, 50];

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function displayDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function compareAddresses(left: string, right: string) {
  const leftParts = left.split(".").map(Number);
  const rightParts = right.split(".").map(Number);
  const ipv4 =
    leftParts.length === 4 &&
    rightParts.length === 4 &&
    [...leftParts, ...rightParts].every(
      (part) => Number.isInteger(part) && part >= 0 && part <= 255,
    );

  if (ipv4) {
    for (let index = 0; index < 4; index += 1) {
      if (leftParts[index] !== rightParts[index]) {
        return leftParts[index] - rightParts[index];
      }
    }
    return 0;
  }
  return left.localeCompare(right);
}

function DeviceDetails({
  device,
  classification,
  onReclassify,
  onClose,
}: {
  device: Device;
  classification: DeviceClassification | undefined;
  onReclassify: (classification: DeviceClassification) => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [classifying, setClassifying] = useState(false);
  const [classificationError, setClassificationError] = useState<ApiError | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
    return () => {
      if (dialog?.open) {
        dialog.close();
      }
    };
  }, []);

  return (
    <dialog
      className="device-dialog"
      ref={dialogRef}
      aria-labelledby="device-dialog-title"
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        dialogRef.current?.close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          dialogRef.current?.close();
        }
      }}
    >
      <div className="dialog-header">
        <div>
          <div className="panel-kicker">DEVICE DETAILS</div>
          <h2 id="device-dialog-title">
            {device.hostname || device.vendor || device.ip_address}
          </h2>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={() => dialogRef.current?.close()}
          aria-label="Close device details"
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>

      <section className="dialog-section" aria-labelledby="identity-title">
        <h3 id="identity-title">Identity</h3>
        <dl className="detail-list">
          <div><dt>Hostname</dt><dd>{device.hostname || "Not reported"}</dd></div>
          <div><dt>IP address</dt><dd>{device.ip_address}</dd></div>
          <div><dt>MAC address</dt><dd>{device.mac_address || "Not reported"}</dd></div>
          <div><dt>Vendor</dt><dd>{device.vendor || "Not reported"}</dd></div>
          <div><dt>Discovery source</dt><dd>{device.discovery_source || "Not reported"}</dd></div>
          <div><dt>First seen</dt><dd>{displayDate(device.first_seen)}</dd></div>
          <div><dt>Last seen</dt><dd>{displayDate(device.last_seen)}</dd></div>
        </dl>
      </section>

      <section className="dialog-section" aria-labelledby="classification-title">
        <h3 id="classification-title">Classification</h3>
        <button
          className="secondary-button"
          type="button"
          disabled={classifying}
          onClick={async () => {
            setClassifying(true);
            setClassificationError(null);
            try {
              onReclassify(await classifyDevice(device.id));
            } catch (error) {
              setClassificationError(toApiError(error));
            } finally {
              setClassifying(false);
            }
          }}
        >
          {classifying ? "Recalculating…" : "Recalculate classification"}
        </button>
        <p className="muted-copy">
          Recalculates from current device data; the backend does not save this result.
        </p>
        {classificationError && <ErrorMessage error={classificationError} />}
        {classification ? (
          <>
            <div className="classification-summary">
              <span className="classification-category">{classification.category}</span>
              <span>{Math.round(classification.confidence * 100)}% confidence</span>
            </div>
            {classification.reasons.length > 0 ? (
              <ul className="evidence-list">
                {classification.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            ) : (
              <p className="muted-copy">The backend did not provide classification evidence.</p>
            )}
            <p className="muted-copy">
              {classification.category === "Unknown"
                ? "There is not enough evidence to classify this device."
                : "This is a best-effort category based on the backend's available device data."}
            </p>
          </>
        ) : (
          <p className="muted-copy">Classification is unavailable for this device.</p>
        )}
      </section>

      <section className="dialog-section" aria-labelledby="metadata-title">
        <h3 id="metadata-title">Additional metadata</h3>
        {device.metadata && Object.keys(device.metadata).length > 0 ? (
          <pre className="metadata-block">{JSON.stringify(device.metadata, null, 2)}</pre>
        ) : (
          <p className="muted-copy">No additional metadata was recorded.</p>
        )}
      </section>
    </dialog>
  );
}

export function DeviceInventoryPage() {
  const [devices, setDevices] = useState<ResourceState<Device[]>>({ status: "loading" });
  const [classifications, setClassifications] = useState<
    ResourceState<DeviceClassification[]>
  >({ status: "loading" });
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sort, setSort] = useState<SortState>({
    key: "last_seen",
    direction: "descending",
  });
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(0);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);

  const loadInventory = useCallback(async () => {
    setDevices({ status: "loading" });
    const [deviceResult, classificationResult] = await Promise.allSettled([
      getDevices(),
      getClassifications(),
    ]);

    setDevices(
      deviceResult.status === "fulfilled"
        ? { status: "ready", data: deviceResult.value }
        : { status: "error", error: toApiError(deviceResult.reason) },
    );
    setClassifications(
      classificationResult.status === "fulfilled"
        ? { status: "ready", data: classificationResult.value }
        : { status: "error", error: toApiError(classificationResult.reason) },
    );
  }, []);

  useEffect(() => {
    void loadInventory();
  }, [loadInventory]);

  const classificationByDevice = useMemo(
    () =>
      new Map(
        classifications.status === "ready"
          ? classifications.data.map((item) => [item.device_id, item])
          : [],
      ),
    [classifications],
  );

  const categoryOptions = useMemo(
    () =>
      Array.from(
        new Set(
          classifications.status === "ready"
            ? classifications.data.map((item) => item.category)
            : [],
        ),
      ).sort((a, b) => a.localeCompare(b)),
    [classifications],
  );

  const sourceOptions = useMemo(
    () =>
      Array.from(
        new Set(
          devices.status === "ready"
            ? devices.data
                .map((device) => device.discovery_source)
                .filter((source): source is string => Boolean(source))
            : [],
        ),
      ).sort((a, b) => a.localeCompare(b)),
    [devices],
  );

  const filteredDevices = useMemo(() => {
    if (devices.status !== "ready") {
      return [];
    }
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return devices.data
      .filter((device) => {
        const classification = classificationByDevice.get(device.id);
        const matchesQuery =
          !normalizedQuery ||
          [
            device.hostname,
            device.ip_address,
            device.mac_address,
            device.vendor,
          ].some((value) => value?.toLocaleLowerCase().includes(normalizedQuery));
        const matchesCategory =
          categoryFilter === "all" ||
          classification?.category === categoryFilter;
        const matchesSource =
          sourceFilter === "all" || device.discovery_source === sourceFilter;
        return matchesQuery && matchesCategory && matchesSource;
      })
      .sort((left, right) => {
        const leftClassification = classificationByDevice.get(left.id);
        const rightClassification = classificationByDevice.get(right.id);
        let comparison = 0;
        if (sort.key === "category") {
          comparison = (leftClassification?.category ?? "Unknown").localeCompare(
            rightClassification?.category ?? "Unknown",
          );
        } else if (sort.key === "last_seen") {
          comparison =
            new Date(left.last_seen).getTime() -
            new Date(right.last_seen).getTime();
        } else if (sort.key === "ip_address") {
          comparison = compareAddresses(left.ip_address, right.ip_address);
        } else {
          comparison = (left[sort.key] ?? "").localeCompare(
            right[sort.key] ?? "",
          );
        }
        return sort.direction === "ascending" ? comparison : -comparison;
      });
  }, [
    categoryFilter,
    classificationByDevice,
    devices,
    query,
    sort,
    sourceFilter,
  ]);

  useEffect(() => {
    setPage(0);
  }, [query, categoryFilter, sourceFilter, pageSize]);

  const pageCount = Math.max(1, Math.ceil(filteredDevices.length / pageSize));
  const visibleDevices = filteredDevices.slice(
    page * pageSize,
    (page + 1) * pageSize,
  );

  const toggleSort = (key: SortKey) => {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "ascending"
          ? "descending"
          : "ascending",
    }));
  };

  const sortButton = (key: SortKey, label: string) => (
    <button
      className="table-sort"
      type="button"
      onClick={() => toggleSort(key)}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <span aria-hidden="true">
        {sort.key !== key ? "↕" : sort.direction === "ascending" ? "↑" : "↓"}
      </span>
    </button>
  );

  const selectedClassification = selectedDevice
    ? classificationByDevice.get(selectedDevice.id)
    : undefined;

  const updateClassification = (classification: DeviceClassification) => {
    setClassifications((current) => ({
      status: "ready",
      data: [
        ...(current.status === "ready"
          ? current.data.filter((item) => item.device_id !== classification.device_id)
          : []),
        classification,
      ],
    }));
  };

  return (
    <section className="inventory-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> NETWORK INVENTORY</div>
          <h1>Connected <span>devices.</span></h1>
          <p className="page-description">
            Review known devices and the evidence behind their classifications.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => void loadInventory()}
          disabled={devices.status === "loading"}
        >
          <Icon name="refresh" size={16} />
          <span>{devices.status === "loading" ? "Loading…" : "Refresh inventory"}</span>
        </button>
      </div>

      <div className="inventory-callout">
        <Icon name="lock" size={17} />
        <span>Read-only inventory. Classification is a best-effort hint, not a threat verdict.</span>
      </div>

      {devices.status === "loading" ? (
        <div className="panel inventory-state" role="status">
          <LoadingValue /><span>Loading device inventory…</span>
        </div>
      ) : devices.status === "error" ? (
        <div className="panel inventory-state inventory-error">
          <ErrorMessage error={devices.error} />
          <button className="secondary-button" type="button" onClick={() => void loadInventory()}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <div className="panel inventory-panel">
            <div className="inventory-toolbar">
              <label className="search-control">
                <span>Search devices</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Hostname, IP, MAC, or vendor"
                />
              </label>
              <label className="filter-control">
                <span>Classification</span>
                <select
                  value={categoryFilter}
                  onChange={(event) => setCategoryFilter(event.target.value)}
                  disabled={classifications.status !== "ready"}
                >
                  <option value="all">All classifications</option>
                  {categoryOptions.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </label>
              <label className="filter-control">
                <span>Discovery source</span>
                <select
                  value={sourceFilter}
                  onChange={(event) => setSourceFilter(event.target.value)}
                >
                  <option value="all">All sources</option>
                  {sourceOptions.map((source) => (
                    <option key={source} value={source}>{source}</option>
                  ))}
                </select>
              </label>
            </div>

            {classifications.status === "error" && (
              <div className="classification-warning">
                Classification data could not be loaded. Device identity details remain available.
                <ErrorMessage error={classifications.error} />
              </div>
            )}

            <div className="inventory-table-wrap">
              <table className="device-table inventory-table">
                <thead>
                  <tr>
                    <th aria-sort={sort.key === "hostname" ? sort.direction : "none"}>{sortButton("hostname", "Device")}</th>
                    <th aria-sort={sort.key === "ip_address" ? sort.direction : "none"}>{sortButton("ip_address", "IP address")}</th>
                    <th>MAC address</th>
                    <th aria-sort={sort.key === "vendor" ? sort.direction : "none"}>{sortButton("vendor", "Vendor")}</th>
                    <th aria-sort={sort.key === "category" ? sort.direction : "none"}>{sortButton("category", "Classification")}</th>
                    <th aria-sort={sort.key === "last_seen" ? sort.direction : "none"}>{sortButton("last_seen", "Last seen")}</th>
                    <th>Source</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDevices.map((device) => {
                    const classification = classificationByDevice.get(device.id);
                    return (
                      <tr key={device.id}>
                        <td>
                          <span className="device-name-cell">
                            <span className="device-avatar"><Icon name="devices" size={16} /></span>
                            <span><strong>{device.hostname || "Unknown device"}</strong><small>Device #{device.id}</small></span>
                          </span>
                        </td>
                        <td className="ip-address">{device.ip_address}</td>
                        <td className="ip-address">{device.mac_address || "—"}</td>
                        <td>{device.vendor || "—"}</td>
                        <td>
                          <span className={`classification-pill${classification?.category === "Unknown" ? " is-unknown" : ""}`}>
                            {classifications.status === "error"
                              ? "Unavailable"
                              : classification?.category ?? "Unknown"}
                          </span>
                          {classification && (
                            <small className="confidence-label">
                              {Math.round(classification.confidence * 100)}% confidence
                            </small>
                          )}
                        </td>
                        <td className="last-seen">{displayDate(device.last_seen)}</td>
                        <td>{device.discovery_source || "—"}</td>
                        <td>
                          <button
                            className="details-button"
                            type="button"
                            onClick={() => setSelectedDevice(device)}
                            aria-label={`View details for ${device.hostname || device.ip_address}`}
                          >
                            Details
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {visibleDevices.length === 0 && (
                    <tr>
                      <td colSpan={8}>
                        <div className="empty-state table-empty">
                          <span className="empty-icon"><Icon name="devices" size={20} /></span>
                          <strong>{devices.data.length === 0 ? "No devices in inventory" : "No matching devices"}</strong>
                          <span>
                            {devices.data.length === 0
                              ? "No devices have been registered yet. You can start a LAN discovery scan when ready."
                              : "Try changing the search text or filters."}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="pagination-bar">
              <span>
                {filteredDevices.length === 0
                  ? "0 devices"
                  : `Showing ${page * pageSize + 1}–${Math.min(
                      (page + 1) * pageSize,
                      filteredDevices.length,
                    )} of ${filteredDevices.length} returned`}
              </span>
              <label>
                Rows
                <select
                  value={pageSize}
                  onChange={(event) => setPageSize(Number(event.target.value))}
                  aria-label="Rows per page"
                >
                  {pageSizes.map((size) => <option key={size} value={size}>{size}</option>)}
                </select>
              </label>
              <div className="pagination-buttons">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
                  disabled={page === 0}
                >
                  Previous
                </button>
                <span>Page {page + 1} of {pageCount}</span>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
                  disabled={page >= pageCount - 1}
                >
                  Next
                </button>
              </div>
            </div>
            {devices.data.length === 200 && (
              <p className="inventory-limit-note">
                The API returned its 200-device page limit. This may not be the complete inventory.
              </p>
            )}
          </div>
        </>
      )}

      {selectedDevice && (
        <DeviceDetails
          device={selectedDevice}
          classification={selectedClassification}
          onReclassify={updateClassification}
          onClose={() => setSelectedDevice(null)}
        />
      )}
    </section>
  );
}
