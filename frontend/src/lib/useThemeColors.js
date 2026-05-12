import { useEffect, useState } from "react";

/**
 * Resolves theme CSS variables to literal hex/hsl strings for places that
 * cannot consume CSS variables directly — primarily SVG attributes used by
 * Recharts (`fill`, `stroke`) and any third-party libs that expect raw colours.
 *
 * Re-evaluates whenever the `data-theme` attribute on <html> changes so the
 * Settings page theme switcher works without a reload.
 */
export function useThemeColors() {
  const read = () => {
    if (typeof window === "undefined") return {};
    const cs = getComputedStyle(document.documentElement);
    const keys = [
      "c-bg",
      "c-bg-alt",
      "c-card",
      "c-surface",
      "c-border",
      "c-ink",
      "c-muted",
      "c-muted-2",
      "c-primary",
      "c-primary-deep",
      "c-primary-soft",
      "c-success",
      "c-danger",
      "c-danger-deep",
      "c-accent",
      "c-accent-2",
      "c-warn",
      "c-on-primary",
    ];
    return Object.fromEntries(
      keys.map((k) => [k, (cs.getPropertyValue(`--${k}`) || "").trim()]),
    );
  };

  const [colors, setColors] = useState(read);

  useEffect(() => {
    setColors(read());
    const obs = new MutationObserver(() => setColors(read()));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);

  return colors;
}
