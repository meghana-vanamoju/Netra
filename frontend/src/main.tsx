import { createRoot } from "react-dom/client";
import App from "./App";
import { LocalizationProvider } from "./localization";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Netra app root element is missing.");
}

createRoot(rootElement).render(
  <LocalizationProvider>
    <App />
  </LocalizationProvider>,
);
