// Light is the default; dark is remembered in localStorage. Every storage access is wrapped:
// the app must work without it. index.html applies the saved theme before first paint.
export type Theme = "dark" | "light";

export const THEME_KEY = "medsafe.theme";
const THEME_COLOR: Record<Theme, string> = { light: "#f6f6f7", dark: "#121212" };

export function readTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage blocked; the theme still applies for this visit.
  }
}
