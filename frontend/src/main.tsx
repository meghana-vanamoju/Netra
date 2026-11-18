import { createRoot } from "react-dom/client";
import App from "./App";
import { LocalizationProvider } from "./localization";
import { NetworkProvider } from "./NetworkContext";
import { ThemeProvider } from "./theme";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Netra app root element is missing.");
}

createRoot(rootElement).render(
  <ThemeProvider>
    <LocalizationProvider>
      <NetworkProvider>
        <App />
      </NetworkProvider>
    </LocalizationProvider>
  </ThemeProvider>,
);
