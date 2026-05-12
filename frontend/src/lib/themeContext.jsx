import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export const THEMES = [
  {
    id: "sage",
    name: "Sage",
    description: "Warm earth tones with olive green. The classic Ledgerly look.",
    swatch: ["#FDFBF7", "#364C2E", "#D1A77E", "#1F2E1B"],
    mode: "light",
  },
  {
    id: "midnight",
    name: "Midnight",
    description: "Deep slate dark mode with emerald accents — easy on the eyes.",
    swatch: ["#0F1419", "#4ADE80", "#FCD34D", "#E8EEF2"],
    mode: "dark",
  },
  {
    id: "ocean",
    name: "Ocean",
    description: "Cool and crisp — light blue-grey paired with deep teal.",
    swatch: ["#F4F8FB", "#0F6F8F", "#F2B544", "#0F2235"],
    mode: "light",
  },
  {
    id: "aurora",
    name: "Aurora",
    description: "Deep violet dark mode with vibrant lavender highlights.",
    swatch: ["#131127", "#B591F5", "#F4C77B", "#F0EBFF"],
    mode: "dark",
  },
];

const THEME_STORAGE_KEY = "ledgerly.theme";

function applyTheme(themeId) {
  const valid = THEMES.find((t) => t.id === themeId) ? themeId : "sage";
  document.documentElement.setAttribute("data-theme", valid);
  const mode = THEMES.find((t) => t.id === valid)?.mode ?? "light";
  // Toggle Tailwind's `dark` class for any shadcn primitives that key off it.
  if (mode === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}

const ThemeContext = createContext({
  theme: "sage",
  setTheme: () => {},
  themes: THEMES,
});

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    if (typeof window === "undefined") return "sage";
    return localStorage.getItem(THEME_STORAGE_KEY) || "sage";
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* localStorage may be blocked in some embed contexts; ignore. */
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
