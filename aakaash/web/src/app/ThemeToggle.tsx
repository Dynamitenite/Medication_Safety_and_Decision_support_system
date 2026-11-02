import { useState } from "react";
import { Moon, Sun } from "@phosphor-icons/react";
import { applyTheme, readTheme, type Theme } from "./theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const next: Theme = theme === "dark" ? "light" : "dark";
  const Glyph = next === "dark" ? Moon : Sun;
  return (
    <button
      type="button"
      className="btn btn-secondary theme-toggle"
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
    >
      <Glyph size={16} />
      {next === "dark" ? "Dark theme" : "Light theme"}
    </button>
  );
}
