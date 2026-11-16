import type { ReactNode } from "react";
import type { ApiError } from "../types";

type IconName =
  | "grid"
  | "devices"
  | "pulse"
  | "shield"
  | "refresh"
  | "arrow"
  | "router"
  | "lock"
  | "check"
  | "alert";

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    devices: <><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></>,
    pulse: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.5 9A7 7 0 0 1 17 6l3 6M4 12l3 6a7 7 0 0 0 11.5-3" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
    router: <><rect x="3" y="8" width="18" height="11" rx="2" /><path d="M7 8V5m10 3V5M7 13h.01M11 13h.01M15 13h.01M8 16h8" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 1 1 8 0v3m-4 4v3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="M10.3 3.9 1.8 18.1A2 2 0 0 0 3.5 21h17a2 2 0 0 0 1.7-2.9L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 4h.01" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export function ErrorMessage({ error }: { error: ApiError }) {
  return (
    <div className="inline-error" role="alert">
      <Icon name="alert" size={16} />
      <span>{error.message}</span>
    </div>
  );
}

export function LoadingValue() {
  return <span className="loading-value" aria-label="Loading" />;
}
