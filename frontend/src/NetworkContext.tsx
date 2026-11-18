import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type NetworkContextValue = {
  selectedSubnet: string | null;
  selectedDeviceId: number | null;
  setSelectedSubnet: (subnet: string | null) => void;
  setSelectedDeviceId: (deviceId: number | null) => void;
  clearNetworkContext: () => void;
};

const defaultNetworkContext: NetworkContextValue = {
  selectedSubnet: null,
  selectedDeviceId: null,
  setSelectedSubnet: () => {},
  setSelectedDeviceId: () => {},
  clearNetworkContext: () => {},
};

const NetworkContext = createContext<NetworkContextValue>(defaultNetworkContext);

const SUBNET_KEY = "netra.selectedSubnet";
const DEVICE_KEY = "netra.selectedDeviceId";

export function NetworkProvider({ children }: { children: ReactNode }) {
  const [selectedSubnet, setSelectedSubnetState] = useState<string | null>(() => {
    const value = window.sessionStorage.getItem(SUBNET_KEY);
    return value && value.trim() ? value.trim() : null;
  });
  const [selectedDeviceId, setSelectedDeviceIdState] = useState<number | null>(() => {
    const value = window.sessionStorage.getItem(DEVICE_KEY);
    const parsed = value ? Number(value) : NaN;
    return Number.isFinite(parsed) ? parsed : null;
  });

  const setSelectedDeviceId = useCallback((deviceId: number | null) => {
    setSelectedDeviceIdState(deviceId);
    if (deviceId === null) {
      window.sessionStorage.removeItem(DEVICE_KEY);
    } else {
      window.sessionStorage.setItem(DEVICE_KEY, String(deviceId));
    }
  }, []);

  const setSelectedSubnet = useCallback((subnet: string | null) => {
    const normalized = subnet?.trim() || null;
    setSelectedSubnetState((current) => {
      if (normalized !== current) {
        setSelectedDeviceIdState(null);
        window.sessionStorage.removeItem(DEVICE_KEY);
      }
      return normalized;
    });
    if (normalized) {
      window.sessionStorage.setItem(SUBNET_KEY, normalized);
    } else {
      window.sessionStorage.removeItem(SUBNET_KEY);
    }
  }, []);

  const clearNetworkContext = useCallback(() => {
    setSelectedSubnet(null);
    setSelectedDeviceId(null);
  }, [setSelectedSubnet, setSelectedDeviceId]);

  return (
    <NetworkContext.Provider
      value={{
        selectedSubnet,
        selectedDeviceId,
        setSelectedSubnet,
        setSelectedDeviceId,
        clearNetworkContext,
      }}
    >
      {children}
    </NetworkContext.Provider>
  );
}

export function useNetworkContext() {
  return useContext(NetworkContext);
}
