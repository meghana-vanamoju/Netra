import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
type Resolved = "light" | "dark";

const KEY = "netra.theme";

function getStored(): Theme {
  const v = localStorage.getItem(KEY);
  if (v === "light" || v === "dark" || v === "system") return v;
  return "system";
}

function systemResolved(): Resolved {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void; resolved: Resolved } | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStored);
  const [resolved, setResolved] = useState<Resolved>(() => {
    const t = getStored();
    return t === "system" ? systemResolved() : t;
  });

  useEffect(() => {
    const apply = () => {
      const r = theme === "system" ? systemResolved() : theme;
      setResolved(r);
      document.documentElement.setAttribute("data-theme", r);
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => { if (theme === "system") apply(); };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const setTheme = (t: Theme) => {
    localStorage.setItem(KEY, t);
    setThemeState(t);
  };

  return <Ctx.Provider value={{ theme, setTheme, resolved }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const v = useContext(Ctx);
  if (!v) throw new Error("ThemeProvider missing");
  return v;
}

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  return (
    <label className="theme-control">
      <span>Theme</span>
      <select aria-label="Theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="system">System</option>
      </select>
    </label>
  );
}