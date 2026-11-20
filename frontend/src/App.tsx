import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./components/AppShell";
import type { AppPage } from "./components/AppShell";
import { DashboardPage } from "./components/DashboardPage";
import { DeviceInventoryPage } from "./components/DeviceInventoryPage";
import { ConnectedDevicesPage } from "./components/ConnectedDevicesPage";
import { DiscoveryPage } from "./components/DiscoveryPage";
import { DnsAnalyticsPage } from "./components/DnsAnalyticsPage";
import { PrivacyAuditPage } from "./components/PrivacyAuditPage";
import { PolicyPlanningPage } from "./components/PolicyPlanningPage";
import { EnforcementRecoveryPage } from "./components/EnforcementRecoveryPage";
import { BandwidthMonitorPage } from "./components/BandwidthMonitorPage";
import { BackupRecoveryPage } from "./components/BackupRecoveryPage";
import { AdGuardDiagnosticsPage } from "./components/AdGuardDiagnosticsPage";
import { SettingsBackendPage } from "./components/SettingsBackendPage";
import { getDatabaseHealth, getHealth } from "./api";

const pages: Record<string, AppPage> = {
  overview: "overview",
  devices: "devices",
  "connected-devices": "connected-devices",
  discovery: "discovery",
  "dns-activity": "dns-activity",
  "privacy-audit": "privacy-audit",
  "policy-planning": "policy-planning",
  "enforcement-recovery": "enforcement-recovery",
  bandwidth: "bandwidth",
  backups: "backups",
  "adguard-diagnostics": "adguard-diagnostics",
  "settings-backend": "settings-backend",
};

function pageFromHash(): AppPage {
  const key = window.location.hash.replace(/^#/, "");
  return pages[key] ?? "overview";
}

export default function App() {
  const [health, setHealth] = useState<boolean | null>(null);
  const [page, setPage] = useState<AppPage>(pageFromHash);

  useEffect(() => {
    let active = true;
    void Promise.all([getHealth(), getDatabaseHealth()]).then(
      ([service, database]) => {
        if (active) {
          setHealth(service.status === "ok" && database.status === "ok");
        }
      },
      () => {
        if (active) setHealth(false);
      },
    );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const syncPage = () => setPage(pageFromHash());
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  const navigate = useCallback((nextPage: AppPage) => {
    const hash = `#${nextPage}`;
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setPage(nextPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const renderPage = () => {
    switch (page) {
      case "devices":
        return <DeviceInventoryPage />;
      case "connected-devices":
        return <ConnectedDevicesPage />;
      case "discovery":
        return <DiscoveryPage />;
      case "dns-activity":
        return <DnsAnalyticsPage />;
      case "privacy-audit":
        return <PrivacyAuditPage />;
      case "policy-planning":
        return <PolicyPlanningPage />;
      case "enforcement-recovery":
        return <EnforcementRecoveryPage />;
      case "bandwidth":
        return <BandwidthMonitorPage />;
      case "backups":
        return <BackupRecoveryPage />;
      case "adguard-diagnostics":
        return <AdGuardDiagnosticsPage />;
      case "settings-backend":
        return <SettingsBackendPage />;
      default:
        return <DashboardPage />;
    }
  };

  return (
    <AppShell
      apiOnline={health === true}
      apiChecking={health === null}
      auditCount={null}
      page={page}
      onNavigate={navigate}
    >
      {renderPage()}
    </AppShell>
  );
}
