import type { ReactNode } from "react";
import { Icon } from "./ui";
import "../styles.css";

const navigation = [
  { label: "Overview", icon: "grid" as const, href: "#overview" },
  { label: "Devices", icon: "devices" as const, href: "#devices" },
  { label: "DNS activity", icon: "pulse" as const, href: "#dns-activity" },
  { label: "Privacy audit", icon: "shield" as const, href: "#privacy-audit" },
];

type AppShellProps = {
  apiOnline: boolean;
  apiChecking: boolean;
  auditCount: number | null;
  children: ReactNode;
};

export function AppShell({
  apiOnline,
  apiChecking,
  auditCount,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Netra home">
          <span className="brand-mark"><Icon name="router" size={23} /></span>
          <span className="brand-name">netra<span>.</span></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map((item, index) => (
            <a
              className={`nav-link${index === 0 ? " active" : ""}`}
              href={item.href}
              key={item.label}
              aria-current={index === 0 ? "page" : undefined}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.label === "Privacy audit" && auditCount !== null && (
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
            <strong>Overview</strong>
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
          {navigation.map((item, index) => (
            <a
              className={`mobile-nav-link${index === 0 ? " active" : ""}`}
              href={item.href}
              key={item.label}
            >
              <Icon name={item.icon} size={17} />
              <span>
                {item.label === "DNS activity"
                  ? "DNS"
                  : item.label === "Privacy audit"
                    ? "Audit"
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
