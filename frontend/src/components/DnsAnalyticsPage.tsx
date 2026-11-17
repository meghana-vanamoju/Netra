import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getDevices,
  getDnsDeviceCounts,
  getDnsDomains,
  getDnsEvents,
  getDnsSummary,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import type {
  ApiError,
  Device,
  DnsDeviceCount,
  DnsDomainCount,
  DnsEvent,
  DnsSummary,
  ResourceState,
} from "../types";

const EVENT_PAGE_SIZE = 50;

function toApiError(error: unknown): ApiError {
  return error instanceof Error
    ? error
    : new Error(`Unexpected API error: ${String(error)}`);
}

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function categoryClass(category: string | null | undefined) {
  switch (category?.toLocaleLowerCase()) {
    case "advertising":
      return "dns-category-advertising";
    case "tracking/analytics":
      return "dns-category-tracking";
    case "telemetry":
      return "dns-category-telemetry";
    default:
      return "dns-category-unknown";
  }
}

function CategoryBreakdown({ summary }: { summary: DnsSummary }) {
  const entries = Object.entries(summary.by_category).sort(
    (left, right) => right[1] - left[1],
  );
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (entries.length === 0 || total === 0) {
    return (
      <LocalizedTree>
      <div className="dns-empty-inline">
        <span className="empty-icon"><Icon name="pulse" size={19} /></span>
        <strong>No categorized DNS events</strong>
        <span>Category totals will appear when the backend has recorded DNS events.</span>
      </div>
      </LocalizedTree>
    );
  }

  return (
    <LocalizedTree>
    <div className="dns-category-list">
      {entries.map(([category, count]) => {
        const percent = (count / total) * 100;
        return (
          <div className="dns-category-row" key={category}>
            <div className="dns-category-label">
              <span className={`dns-category-dot ${categoryClass(category)}`} />
              <span>{category}</span>
              <strong>{number(count)}</strong>
              <span className="dns-percent">{Math.round(percent)}%</span>
            </div>
            <div
              className="dns-category-track"
              role="img"
              aria-label={`${category}: ${number(count)} events, ${Math.round(percent)} percent`}
            >
              <span
                className={`dns-category-bar ${categoryClass(category)}`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        );
      })}
      <p className="dns-chart-caption">
        Categories are assigned by the backend's domain matching rules. “Unknown”
        means no rule matched; it is not a maliciousness verdict.
      </p>
    </div>
    </LocalizedTree>
  );
}

export function DnsAnalyticsPage() {
  const [summary, setSummary] = useState<ResourceState<DnsSummary>>({
    status: "loading",
  });
  const [domains, setDomains] = useState<ResourceState<DnsDomainCount[]>>({
    status: "loading",
  });
  const [deviceCounts, setDeviceCounts] = useState<
    ResourceState<DnsDeviceCount[]>
  >({ status: "loading" });
  const [devices, setDevices] = useState<ResourceState<Device[]>>({
    status: "loading",
  });
  const [events, setEvents] = useState<ResourceState<DnsEvent[]>>({
    status: "loading",
  });
  const [refreshing, setRefreshing] = useState(false);
  const [domainQuery, setDomainQuery] = useState("");
  const [eventQuery, setEventQuery] = useState("");
  const [eventCategory, setEventCategory] = useState("all");
  const [eventDeviceId, setEventDeviceId] = useState("");
  const [eventOffset, setEventOffset] = useState(0);
  const [eventReload, setEventReload] = useState(0);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    setSummary({ status: "loading" });
    setDomains({ status: "loading" });
    setDeviceCounts({ status: "loading" });
    setDevices({ status: "loading" });

    const [summaryResult, domainsResult, deviceCountsResult, devicesResult] =
      await Promise.allSettled([
        getDnsSummary(),
        getDnsDomains(20),
        getDnsDeviceCounts(),
        getDevices(),
      ]);

    setSummary(
      summaryResult.status === "fulfilled"
        ? { status: "ready", data: summaryResult.value }
        : { status: "error", error: toApiError(summaryResult.reason) },
    );
    setDomains(
      domainsResult.status === "fulfilled"
        ? { status: "ready", data: domainsResult.value }
        : { status: "error", error: toApiError(domainsResult.reason) },
    );
    setDeviceCounts(
      deviceCountsResult.status === "fulfilled"
        ? { status: "ready", data: deviceCountsResult.value }
        : { status: "error", error: toApiError(deviceCountsResult.reason) },
    );
    setDevices(
      devicesResult.status === "fulfilled"
        ? { status: "ready", data: devicesResult.value }
        : { status: "error", error: toApiError(devicesResult.reason) },
    );
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    let active = true;
    setEvents({ status: "loading" });

    void getDnsEvents({
      limit: EVENT_PAGE_SIZE,
      offset: eventOffset,
      ...(eventDeviceId ? { deviceId: Number(eventDeviceId) } : {}),
    }).then(
      (data) => {
        if (active) {
          setEvents({ status: "ready", data });
        }
      },
      (error: unknown) => {
        if (active) {
          setEvents({ status: "error", error: toApiError(error) });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [eventDeviceId, eventOffset, eventReload]);

  const devicesById = useMemo(
    () =>
      new Map(
        devices.status === "ready"
          ? devices.data.map((device) => [device.id, device])
          : [],
      ),
    [devices],
  );

  const domainMatches = useMemo(() => {
    if (domains.status !== "ready") {
      return [];
    }
    const query = domainQuery.trim().toLocaleLowerCase();
    return domains.data.filter((entry) => entry.domain.toLocaleLowerCase().includes(query));
  }, [domainQuery, domains]);

  const eventCategories = useMemo(
    () => {
      const categories =
        summary.status === "ready"
          ? Object.keys(summary.data.by_category)
          : [];
      const pageCategories =
        events.status === "ready"
          ? events.data.map((event) => event.category || "Unknown")
          : [];
      return Array.from(new Set([...categories, ...pageCategories])).sort(
        (a, b) => a.localeCompare(b),
      );
    },
    [events, summary],
  );

  const filteredEvents = useMemo(() => {
    if (events.status !== "ready") {
      return [];
    }
    const query = eventQuery.trim().toLocaleLowerCase();
    return events.data.filter((event) => {
      const category = event.category || "Unknown";
      const device = event.device_id === null ? undefined : devicesById.get(event.device_id);
      const deviceName = device?.hostname || device?.ip_address || "";
      return (
        (!query ||
          event.domain.toLocaleLowerCase().includes(query) ||
          deviceName.toLocaleLowerCase().includes(query) ||
          String(event.device_id ?? "").includes(query)) &&
        (eventCategory === "all" || category === eventCategory)
      );
    });
  }, [devicesById, eventCategory, eventQuery, events]);

  const eventPageMayContinue =
    events.status === "ready" && events.data.length === EVENT_PAGE_SIZE;
  const isEmpty =
    summary.status === "ready" &&
    summary.data.total === 0 &&
    domains.status === "ready" &&
    domains.data.length === 0 &&
    deviceCounts.status === "ready" &&
    deviceCounts.data.length === 0;
  const selectedDeviceName = eventDeviceId
    ? devicesById.get(Number(eventDeviceId))?.hostname ||
      devicesById.get(Number(eventDeviceId))?.ip_address ||
      `Device #${eventDeviceId}`
    : null;

  const selectDeviceEvents = (deviceId: number | null) => {
    setEventDeviceId(deviceId === null ? "" : String(deviceId));
    setEventOffset(0);
    setEventQuery("");
    setEventCategory("all");
    document.getElementById("dns-events")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const deviceEntries =
    deviceCounts.status === "ready"
      ? [...deviceCounts.data].sort((a, b) => b.count - a.count)
      : [];
  const maxDeviceCount = Math.max(1, ...deviceEntries.map((entry) => entry.count));

  return (
    <LocalizedTree>
    <section className="dns-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> NETWORK ACTIVITY</div>
          <h1>DNS <span>analytics.</span></h1>
          <p className="page-description">
            Explore recorded DNS queries and backend domain categories. No traffic is collected by this page.
          </p>
        </div>
        <button
          className="refresh-button"
          type="button"
          onClick={() => {
            void loadOverview();
            setEventReload((version) => version + 1);
          }}
          disabled={refreshing}
        >
          <Icon name="refresh" size={16} />
          <span>{refreshing ? "Refreshing…" : "Refresh analytics"}</span>
        </button>
      </div>

      <div className="dns-readonly-note">
        <Icon name="lock" size={16} />
        <span>Read-only analytics from stored events. No DNS queries are sent and no network settings are changed.</span>
      </div>

      {isEmpty && (
        <div className="dns-empty-banner">
          <span className="empty-icon"><Icon name="pulse" size={20} /></span>
          <div>
            <strong>No DNS activity recorded</strong>
            <span>Analytics will appear after the backend has stored DNS events.</span>
          </div>
        </div>
      )}

      <section className="metric-grid dns-metric-grid" aria-label="DNS analytics summary">
        <article className="metric-card">
          <div className="metric-top">
            <span className="metric-label">DNS EVENTS</span>
            <span className="metric-icon violet"><Icon name="pulse" size={18} /></span>
          </div>
          <div className="metric-value">
            {summary.status === "ready" ? number(summary.data.total) : summary.status === "loading" ? <LoadingValue /> : "—"}
          </div>
          <div className="metric-foot">
            <span>Recorded events across the network</span>
          </div>
          {summary.status === "error" && <ErrorMessage error={summary.error} />}
        </article>
        <article className="metric-card">
          <div className="metric-top">
            <span className="metric-label">UNIQUE DOMAINS</span>
            <span className="metric-icon blue"><Icon name="grid" size={17} /></span>
          </div>
          <div className="metric-value">
            {summary.status === "ready" ? number(summary.data.unique_domains) : summary.status === "loading" ? <LoadingValue /> : "—"}
          </div>
          <div className="metric-foot"><span>Distinct domains in recorded events</span></div>
          {summary.status === "error" && <ErrorMessage error={summary.error} />}
        </article>
        <article className="metric-card">
          <div className="metric-top">
            <span className="metric-label">CATEGORIES OBSERVED</span>
            <span className="metric-icon amber"><Icon name="shield" size={17} /></span>
          </div>
          <div className="metric-value">
            {summary.status === "ready" ? number(Object.keys(summary.data.by_category).length) : summary.status === "loading" ? <LoadingValue /> : "—"}
          </div>
          <div className="metric-foot"><span>Backend-assigned event categories</span></div>
          {summary.status === "error" && <ErrorMessage error={summary.error} />}
        </article>
        <article className="metric-card">
          <div className="metric-top">
            <span className="metric-label">DEVICE GROUPS</span>
            <span className="metric-icon green"><Icon name="devices" size={18} /></span>
          </div>
          <div className="metric-value">
            {deviceCounts.status === "ready" ? number(deviceCounts.data.length) : deviceCounts.status === "loading" ? <LoadingValue /> : "—"}
          </div>
          <div className="metric-foot"><span>Includes unlinked events if present</span></div>
          {deviceCounts.status === "error" && <ErrorMessage error={deviceCounts.error} />}
        </article>
      </section>

      <section className="dns-analytics-grid">
        <article className="panel dns-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">AGGREGATED DATA</div>
              <h2>Queries by category</h2>
            </div>
            <span className="read-only-tag">SUMMARY</span>
          </div>
          {summary.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Loading category totals…</span></div>
          ) : summary.status === "error" ? (
            <div className="panel-state"><ErrorMessage error={summary.error} /></div>
          ) : (
            <CategoryBreakdown summary={summary.data} />
          )}
        </article>

        <article className="panel dns-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">AGGREGATED DATA</div>
              <h2>Queries by device</h2>
            </div>
            <span className="read-only-tag">GROUPED</span>
          </div>
          {deviceCounts.status === "loading" || devices.status === "loading" ? (
            <div className="panel-state"><LoadingValue /><span>Loading device totals…</span></div>
          ) : deviceCounts.status === "error" ? (
            <div className="panel-state"><ErrorMessage error={deviceCounts.error} /></div>
          ) : (
            <>
              {devices.status === "error" && <ErrorMessage error={devices.error} />}
              {deviceEntries.length === 0 ? (
                <div className="dns-empty-inline">
                  <span className="empty-icon"><Icon name="devices" size={19} /></span>
                  <strong>No device query totals</strong>
                  <span>There are no grouped DNS events to display.</span>
                </div>
              ) : (
                <div className="dns-device-list">
                  {deviceEntries.map((entry) => {
                    const device =
                      entry.device_id === null
                        ? undefined
                        : devicesById.get(entry.device_id);
                    const title =
                      entry.device_id === null
                        ? "Unlinked to inventory"
                        : device?.hostname ||
                          device?.ip_address ||
                          `Device #${entry.device_id}`;
                    return (
                      <div className="dns-device-row" key={entry.device_id ?? "unlinked"}>
                        <div className="dns-device-title">
                          <span
                            data-no-translate={
                              entry.device_id !== null &&
                              Boolean(device?.hostname || device?.ip_address)
                                ? "true"
                                : undefined
                            }
                          >
                            {title}
                          </span>
                          {entry.device_id !== null && (
                            <span className="dns-device-subtitle">
                              {device?.ip_address
                                ? <span data-no-translate="true">{device.ip_address}</span>
                                : `Device #${entry.device_id}`}
                            </span>
                          )}
                        </div>
                        <div
                          className="dns-device-track"
                          role="img"
                          aria-label={`${title}: ${number(entry.count)} DNS events`}
                        >
                          <span style={{ width: `${(entry.count / maxDeviceCount) * 100}%` }} />
                        </div>
                        <strong>{number(entry.count)}</strong>
                        {entry.device_id !== null && (
                          <button
                            className="text-link dns-device-link"
                            type="button"
                            onClick={() => selectDeviceEvents(entry.device_id)}
                          >
                            Events
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="dns-chart-caption">
                Events without a matched inventory device remain grouped as unlinked.
              </p>
            </>
          )}
        </article>
      </section>

      <section className="panel dns-domains-panel">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">AGGREGATED DATA</div>
            <h2>Top domains</h2>
          </div>
          <span className="read-only-tag">TOP 20</span>
        </div>
        <label className="search-control dns-domain-search">
          <span>Filter listed domains</span>
          <input
            type="search"
            value={domainQuery}
            onChange={(event) => setDomainQuery(event.target.value)}
            placeholder="Search domain"
          />
        </label>
        {domains.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Loading domain totals…</span></div>
        ) : domains.status === "error" ? (
          <div className="panel-state"><ErrorMessage error={domains.error} /></div>
        ) : domainMatches.length === 0 ? (
          <div className="dns-empty-inline">
            <span className="empty-icon"><Icon name="grid" size={19} /></span>
            <strong>{domains.data.length === 0 ? "No domains recorded" : "No domains match"}</strong>
            <span>
              {domains.data.length === 0
                ? "The backend has no domain aggregates to show."
                : "Try a different search term."}
            </span>
          </div>
        ) : (
          <>
            <div className="inventory-table-wrap">
              <table className="device-table dns-domain-table">
                <thead>
                  <tr><th>DOMAIN</th><th>CATEGORY</th><th>QUERY COUNT</th></tr>
                </thead>
                <tbody>
                  {domainMatches.map((entry) => (
                    <tr key={entry.domain}>
                      <td className="dns-domain-name" data-no-translate="true">{entry.domain}</td>
                      <td>
                        <span className={`dns-category-pill ${categoryClass(entry.category)}`}>
                          {entry.category || "Unknown"}
                        </span>
                      </td>
                      <td className="dns-domain-count">{number(entry.count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {domains.data.length === 20 && (
              <p className="dns-chart-caption">Showing the top 20 domains returned by the backend.</p>
            )}
          </>
        )}
      </section>

      <section className="panel dns-events-panel" id="dns-events">
        <div className="panel-header">
          <div>
            <div className="panel-kicker">RAW EVENT RECORDS</div>
            <h2>DNS event explorer</h2>
          </div>
          <span className="read-only-tag">RECORDED EVENTS</span>
        </div>
        <p className="dns-events-description">
          These are individual stored DNS event records, separate from the aggregated summaries above.
        </p>
        {selectedDeviceName && (
          <div className="dns-filter-notice">
            Showing events requested for <strong>{selectedDeviceName}</strong>.
            <button type="button" onClick={() => selectDeviceEvents(null)}>Clear device filter</button>
          </div>
        )}
        <div className="dns-event-filters">
          <label className="search-control">
            <span>Search this event page</span>
            <input
              type="search"
              value={eventQuery}
              onChange={(event) => setEventQuery(event.target.value)}
              placeholder="Domain, device name, or ID"
            />
          </label>
          <label className="filter-control">
            <span>Category</span>
            <select
              value={eventCategory}
              onChange={(event) => setEventCategory(event.target.value)}
              disabled={events.status !== "ready"}
            >
              <option value="all">All categories</option>
              {eventCategories.map((category) => <option value={category} key={category}>{category}</option>)}
            </select>
          </label>
        </div>
        {events.status === "loading" ? (
          <div className="panel-state"><LoadingValue /><span>Loading raw DNS events…</span></div>
        ) : events.status === "error" ? (
          <div className="panel-state"><ErrorMessage error={events.error} /></div>
        ) : filteredEvents.length === 0 ? (
          <div className="dns-empty-inline">
            <span className="empty-icon"><Icon name="pulse" size={19} /></span>
            <strong>{events.data.length === 0 ? "No raw DNS events returned" : "No events match these filters"}</strong>
            <span>
              {events.data.length === 0
                ? "The backend returned no event records for this page."
                : "Search filters apply to this fetched page of events."}
            </span>
          </div>
        ) : (
          <>
            <div className="inventory-table-wrap">
              <table className="device-table dns-event-table">
                <thead>
                  <tr><th>TIME</th><th>DOMAIN</th><th>CATEGORY</th><th>DEVICE</th></tr>
                </thead>
                <tbody>
                  {filteredEvents.map((event) => {
                    const device =
                      event.device_id === null
                        ? undefined
                        : devicesById.get(event.device_id);
                    const deviceLabel =
                      event.device_id === null
                        ? "Unlinked"
                        : device?.hostname ||
                          device?.ip_address ||
                          `Device #${event.device_id}`;
                    return (
                      <tr key={event.id}>
                        <td className="last-seen">{formatTime(event.timestamp)}</td>
                        <td className="dns-domain-name" data-no-translate="true">{event.domain}</td>
                        <td>
                          <span className={`dns-category-pill ${categoryClass(event.category)}`}>
                            {event.category || "Unknown"}
                          </span>
                        </td>
                        <td>
                          {event.device_id === null ? (
                            deviceLabel
                          ) : (
                            <button
                              className="dns-event-device"
                              type="button"
                              onClick={() => selectDeviceEvents(event.device_id)}
                            >
                              {device?.hostname || device?.ip_address
                                ? <span data-no-translate="true">{deviceLabel}</span>
                                : deviceLabel}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="dns-chart-caption">
              Showing matching records from the current page; text and category filters do not search events on other pages.
            </p>
          </>
        )}
        <div className="pagination-bar dns-event-pagination">
          <span>
            {events.status === "ready"
              ? `Page ${eventOffset / EVENT_PAGE_SIZE + 1} · ${filteredEvents.length} matching events shown`
              : "Event page"}
          </span>
          <div className="pagination-buttons">
            <button
              className="secondary-button"
              type="button"
              onClick={() => setEventOffset((offset) => Math.max(0, offset - EVENT_PAGE_SIZE))}
              disabled={eventOffset === 0 || events.status === "loading"}
            >
              Previous
            </button>
            {eventPageMayContinue && <span>More events may be available</span>}
            <button
              className="secondary-button"
              type="button"
              onClick={() => setEventOffset((offset) => offset + EVENT_PAGE_SIZE)}
              disabled={!eventPageMayContinue}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </section>
    </LocalizedTree>
  );
}
