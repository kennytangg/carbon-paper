"use client";

import { useEffect, useState } from "react";

type Mode = "auto" | "light" | "dark";
const NEXT: Record<Mode, Mode> = { auto: "light", light: "dark", dark: "auto" };
const LABEL: Record<Mode, string> = { auto: "Theme: auto", light: "Theme: light", dark: "Theme: dark" };

function apply(mode: Mode) {
  const el = document.documentElement;
  if (mode === "auto") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", mode);
}

export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("auto");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("nc-theme") as Mode | null;
      if (saved === "light" || saved === "dark") setMode(saved);
    } catch {
      /* storage unavailable: stay on auto */
    }
  }, []);
  const next = () => {
    const m = NEXT[mode];
    setMode(m);
    apply(m);
    try {
      if (m === "auto") localStorage.removeItem("nc-theme");
      else localStorage.setItem("nc-theme", m);
    } catch {
      /* ignore */
    }
  };
  return (
    <button type="button" className="theme-btn" onClick={next} aria-label={`${LABEL[mode]}, click to change`}>
      {LABEL[mode]}
    </button>
  );
}
