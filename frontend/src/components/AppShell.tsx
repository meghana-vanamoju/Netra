import type { MouseEvent, ReactNode } from "react";
import { Icon } from "./ui";
import "../styles.css";

export type AppPage = "overview" | "devices" | "discovery" | "dns-activity";

const navigation = [
  { label: "Overview", icon: "grid" as const, href: "#overview", page: "overview" as const },
  { label: "Devices", icon: "devices" as const, href: "#devices", page: "devices" as const },
  { label: "LAN discovery", icon: "pulse" as const, href: "#discovery", page: "discovery" as const },
  { label: "DNS activity", icon: "pulse" as const, href: "#dns-activity", page: "dns-activity" as const },
  { label: "Privacy audit", icon: "shield" as const, href: "#privacy-audit" },
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
  const navigate = (
    event: MouseEvent<HTMLAnchorElement>,
    item: (typeof navigation)[number],
  ) => {
    if (item.page) {
      event.preventDefault();
      onNavigate(item.page);
      return;
    }

    if (page !== "overview") {
      event.preventDefault();
      onNavigate("overview");
      window.setTimeout(() => {
        document.getElementById(item.href.slice(1))?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 0);
    }
  };
  const pageLabel =
    page === "dns-activity"
      ? "DNS activity"
      : page === "devices"
        ? "Devices"
        : page === "discovery"
          ? "LAN discovery"
          : "Overview";

  return (
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
            <strong>{pageLabel}</strong>
          </div>
          <div className="topbar-actions">
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

        <nav className="mobile-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <a
              className={`mobile-nav-link${item.page === page ? " active" : ""}`}
              href={item.href}
              key={item.label}
              onClick={(event) => navigate(event, item)}
            >
              <Icon name={item.icon} size={17} />
              <span>
                {item.label === "DNS activity"
                  ? "DNS"
                  : item.label === "Privacy audit"
                    ? "Audit"
                    : item.label === "LAN discovery"
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
  );
}
