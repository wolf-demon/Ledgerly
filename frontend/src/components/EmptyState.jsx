import React from "react";

/**
 * Standardised empty-state placeholder used throughout the app for
 * "no data yet" panels. Keeps illustration, copy + CTA visually consistent.
 *
 * @param {React.ComponentType} icon  lucide-react icon component
 * @param {string} title
 * @param {string} [description]
 * @param {React.ReactNode} [action]  e.g. <Button>…</Button>
 * @param {string} [testId]
 */
export default function EmptyState({ icon: Icon, title, description, action, testId, className = "" }) {
  return (
    <div
      className={`py-12 px-6 text-center flex flex-col items-center ledger-fade-in ${className}`}
      data-testid={testId}
    >
      {Icon && (
        <div className="w-14 h-14 rounded-full bg-[var(--c-surface)] flex items-center justify-center mb-4">
          <Icon className="w-6 h-6 text-[var(--c-primary)]" />
        </div>
      )}
      <h3 className="text-base font-medium text-[var(--c-ink)]" style={{ fontFamily: "Work Sans" }}>
        {title}
      </h3>
      {description && (
        <p className="text-sm text-[var(--c-muted)] mt-1 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
