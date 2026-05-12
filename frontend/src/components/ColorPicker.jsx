import React from "react";

/**
 * Curated category color palette.
 * Hand-picked for readability against both light and dark themes.
 * Grouped by hue family.
 */
export const CATEGORY_COLORS = [
  // Greens
  "#364C2E", "#4B6B40", "#728A66", "#A3B58B", "#1E5128", "#3E885B", "#7FB069",
  // Teals / blues
  "#0F6F8F", "#3CABA6", "#5BA8C0", "#1F4068", "#3E64C1", "#7C9CD8",
  // Purples
  "#5A4A8F", "#8B5CF6", "#B591F5", "#C4B5FD", "#6D4F8E",
  // Pinks / reds
  "#D96C4E", "#C0593E", "#E0506C", "#F472B6", "#B83C5E", "#FB7185",
  // Yellows / ambers
  "#F2B544", "#D1A77E", "#E3C8AA", "#FBBF24", "#F59E0B", "#FCD34D",
  // Browns / earth
  "#8B5E3C", "#9E7B58", "#5D4037", "#A57C52", "#6E4E2E",
  // Neutrals
  "#656C5A", "#9E988C", "#475569", "#1F2E1B", "#2A3543",
];

/**
 * Color picker grid for choosing a category colour.
 *
 * @param {string} value     currently-selected hex
 * @param {(hex: string) => void} onChange
 * @param {string} [testId]
 */
export default function ColorPicker({ value, onChange, testId = "color-picker" }) {
  return (
    <div className="grid grid-cols-10 gap-1.5" data-testid={testId}>
      {CATEGORY_COLORS.map((hex) => {
        const selected = hex.toLowerCase() === (value || "").toLowerCase();
        return (
          <button
            key={hex}
            type="button"
            onClick={() => onChange(hex)}
            data-testid={`color-${hex.replace("#", "").toLowerCase()}`}
            className={`relative w-7 h-7 rounded-md transition-all duration-150 hover:scale-110 hover:shadow-md ${
              selected ? "ring-2 ring-offset-2 ring-offset-[var(--c-card)] ring-[var(--c-primary)]" : ""
            }`}
            style={{ backgroundColor: hex }}
            aria-label={`Choose colour ${hex}`}
            title={hex}
          >
            {selected && (
              <span
                className="absolute inset-0 flex items-center justify-center text-[10px] font-bold"
                style={{ color: "#FFFFFF", textShadow: "0 1px 2px rgba(0,0,0,0.4)" }}
              >
                ✓
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
