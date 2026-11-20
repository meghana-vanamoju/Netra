import { useEffect, useRef, type MouseEvent, type ReactNode } from "react";
import { Icon } from "./ui";
import { LanguageSelector, LocalizedTree } from "../localization";
import { ThemeSelector } from "../theme";
import { useNetworkContext } from "../NetworkContext";
import "../styles.css";

export type AppPage =
  | "overview"
  | "devices"
  | "connected-devices"
  | "discovery"
  | "dns-activity"
  | "privacy-audit"
  | "policy-planning"
  | "enforcement-recovery"
  | "bandwidth"
  | "backups"
  | "adguard-diagnostics"
  | "settings-backend";

const navigation = [
  { label: "Overview", icon: "grid" as const, href: "#overview", page: "overview" as const },
  { label: "Devices", icon: "devices" as const, href: "#devices", page: "devices" as const },
  { label: "Connected Devices", icon: "devices" as const, href: "#connected-devices", page: "connected-devices" as const },
  { label: "LAN discovery", icon: "pulse" as const, href: "#discovery", page: "discovery" as const },
  { label: "DNS protection", icon: "shield" as const, href: "#dns-activity", page: "dns-activity" as const },
  { label: "Privacy audit", icon: "shield" as const, href: "#privacy-audit", page: "privacy-audit" as const },
  { label: "Device policies", icon: "shield" as const, href: "#policy-planning", page: "policy-planning" as const },
  { label: "Enforcement readiness", icon: "lock" as const, href: "#enforcement-recovery", page: "enforcement-recovery" as const },
  { label: "Bandwidth monitor", icon: "pulse" as const, href: "#bandwidth", page: "bandwidth" as const },
  { label: "Backup & recovery", icon: "lock" as const, href: "#backups", page: "backups" as const },
  { label: "AdGuard diagnostics", icon: "router" as const, href: "#adguard-diagnostics", page: "adguard-diagnostics" as const },
  { label: "Settings & backend", icon: "router" as const, href: "#settings-backend", page: "settings-backend" as const },
];

type AppShellProps = {
  apiOnline: boolean;
  apiChecking: boolean;
  auditCount: number | null;
  page: AppPage;
  onNavigate: (page: AppPage) => void;
  children: ReactNode;
};

export function AppShell({
  apiOnline,
  apiChecking,
  auditCount,
  page,
  onNavigate,
  children,
}: AppShellProps) {
  const mobileNavRef = useRef<HTMLElement>(null);
  const { selectedSubnet, selectedDeviceId } = useNetworkContext();

  useEffect(() => {
    const activeLink = mobileNavRef.current?.querySelector<HTMLElement>(
      '[aria-current="page"]',
    );
    activeLink?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    });
  }, [page]);

  const navigate = (
    event: MouseEvent<HTMLAnchorElement>,
    item: (typeof navigation)[number],
  ) => {
    event.preventDefault();
    onNavigate(item.page);
  };
  const pageLabel: Record<AppPage, string> = {
    overview: "Overview",
    devices: "Devices",
    "connected-devices": "Connected Devices",
    discovery: "LAN discovery",
    "dns-activity": "DNS protection",
    "privacy-audit": "Privacy audit",
    "policy-planning": "Device policies",
    "enforcement-recovery": "Enforcement readiness",
    bandwidth: "Bandwidth monitor",
    backups: "Backup & recovery",
    "adguard-diagnostics": "AdGuard diagnostics",
    "settings-backend": "Settings & backend",
  };

  return (
    <LocalizedTree>
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#overview"
          aria-label="Netra home"
          onClick={(event) => {
            event.preventDefault();
            onNavigate("overview");
          }}
        >
          <span className="brand-mark"><Icon name="router" size={23} /></span>
          <span className="brand-name">netra<span>.</span></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <a
              className={`nav-link${item.page === page ? " active" : ""}`}
              href={item.href}
              key={item.label}
              aria-current={item.page === page ? "page" : undefined}
              onClick={(event) => navigate(event, item)}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.label === "Privacy audit" && auditCount !== null && page === "overview" && (
                <span className="nav-count">{auditCount}</span>
              )}
            </a>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="network-card">
            <span className="network-icon"><Icon name="router" size={17} /></span>
            <div>
              <strong>Home network</strong>
              <span>{apiOnline ? "Connected to Netra" : "Connection status unknown"}</span>
            </div>
            <span className={`connection-dot${apiOnline ? " online" : ""}`} />
          </div>
          <div className="sidebar-version">NETRA <span>·</span> NETWORK GUARDIAN</div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark"><Icon name="router" size={21} /></span>
            <span className="brand-name">netra<span>.</span></span>
          </div>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{pageLabel[page]}</strong>
          </div>
          <div className="topbar-actions">
            <div className="context-chip" title="Selected network context">
              <Icon name="pulse" size={14} />
              <span data-no-translate="true">{selectedSubnet ?? "No subnet selected"}</span>
              {selectedDeviceId !== null && (
                <span className="context-device">Device #{selectedDeviceId}</span>
              )}
            </div>
            <LanguageSelector />
            <ThemeSelector />
            <div
              className={`api-indicator${apiOnline ? "" : apiChecking ? " checking" : " offline"}`}
              role="status"
            >
              <span className="connection-dot" />
              <span>
                {apiChecking
                  ? "Checking connection"
                  : apiOnline
                    ? "API connected"
                    : "API unavailable"}
              </span>
            </div>
            <div className="avatar" aria-label="Netra workspace">N</div>
          </div>
        </header>

        <nav
          className="mobile-nav"
          aria-label="Main navigation"
          ref={mobileNavRef}
        >
          {navigation.map((item) => (
            <a
              className={`mobile-nav-link${item.page === page ? " active" : ""}`}
              href={item.href}
              key={item.label}
              aria-current={item.page === page ? "page" : undefined}
              onClick={(event) => navigate(event, item)}
            >
              <Icon name={item.icon} size={17} />
              <span>
                {item.page === "dns-activity"
                  ? "DNS"
                  : item.page === "connected-devices"
                    ? "Hotspot"
                  : item.page === "privacy-audit"
                    ? "Audit"
                    : item.page === "policy-planning"
                      ? "Policies"
                      : item.page === "enforcement-recovery"
                        ? "Enforce"
                        : item.page === "bandwidth"
                          ? "Traffic"
                          : item.page === "backups"
                            ? "Backups"
                            : item.page === "adguard-diagnostics"
                              ? "Diagnostics"
                              : item.page === "settings-backend"
                                ? "Settings"
                                : item.page === "discovery"
                                  ? "Discover"
                                  : item.label}
              </span>
            </a>
          ))}
        </nav>

        <main className="content" id="overview">
          {children}
        </main>
      </div>
    </div>
    </LocalizedTree>
  );
}
