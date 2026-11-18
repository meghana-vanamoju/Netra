import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NetworkProvider, useNetworkContext } from "./NetworkContext";

function Consumer() {
  const { selectedSubnet, selectedDeviceId, setSelectedSubnet, setSelectedDeviceId, clearNetworkContext } =
    useNetworkContext();
  return (
    <div>
      <span data-testid="subnet">{selectedSubnet ?? "none"}</span>
      <span data-testid="device">{selectedDeviceId === null ? "none" : selectedDeviceId}</span>
      <button type="button" onClick={() => setSelectedSubnet("192.168.1.0/24")}>
        set subnet
      </button>
      <button type="button" onClick={() => setSelectedSubnet("10.0.0.0/24")}>
        switch subnet
      </button>
      <button type="button" onClick={() => setSelectedDeviceId(7)}>
        set device
      </button>
      <button type="button" onClick={() => clearNetworkContext()}>
        clear
      </button>
    </div>
  );
}

describe("NetworkContext", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
  });

  it("persists and hydrates selected subnet and device", async () => {
    const { unmount } = render(
      <NetworkProvider>
        <Consumer />
      </NetworkProvider>,
    );

    expect(screen.getByTestId("subnet").textContent).toBe("none");
    expect(screen.getByTestId("device").textContent).toBe("none");

    fireEvent.click(screen.getByRole("button", { name: "set subnet" }));
    fireEvent.click(screen.getByRole("button", { name: "set device" }));

    await waitFor(() => {
      expect(screen.getByTestId("subnet").textContent).toBe("192.168.1.0/24");
    });
    expect(screen.getByTestId("device").textContent).toBe("7");
    expect(window.sessionStorage.getItem("netra.selectedSubnet")).toBe("192.168.1.0/24");
    expect(window.sessionStorage.getItem("netra.selectedDeviceId")).toBe("7");

    unmount();

    render(
      <NetworkProvider>
        <Consumer />
      </NetworkProvider>,
    );

    expect(screen.getByTestId("subnet").textContent).toBe("192.168.1.0/24");
    expect(screen.getByTestId("device").textContent).toBe("7");
  });

  it("clears the selected device when the subnet changes", async () => {
    render(
      <NetworkProvider>
        <Consumer />
      </NetworkProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "set subnet" }));
    fireEvent.click(screen.getByRole("button", { name: "set device" }));
    fireEvent.click(screen.getByRole("button", { name: "switch subnet" }));

    await waitFor(() => {
      expect(screen.getByTestId("subnet").textContent).toBe("10.0.0.0/24");
    });
    expect(screen.getByTestId("device").textContent).toBe("none");
    expect(window.sessionStorage.getItem("netra.selectedDeviceId")).toBeNull();
  });

  it("clears persisted context", async () => {
    window.sessionStorage.setItem("netra.selectedSubnet", "10.0.0.0/24");
    window.sessionStorage.setItem("netra.selectedDeviceId", "3");

    render(
      <NetworkProvider>
        <Consumer />
      </NetworkProvider>,
    );

    expect(screen.getByTestId("subnet").textContent).toBe("10.0.0.0/24");
    expect(screen.getByTestId("device").textContent).toBe("3");

    fireEvent.click(screen.getByRole("button", { name: "clear" }));

    await waitFor(() => {
      expect(screen.getByTestId("subnet").textContent).toBe("none");
    });
    expect(screen.getByTestId("device").textContent).toBe("none");
    expect(window.sessionStorage.getItem("netra.selectedSubnet")).toBeNull();
    expect(window.sessionStorage.getItem("netra.selectedDeviceId")).toBeNull();
  });
});
