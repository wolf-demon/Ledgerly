import React from "react";

/**
 * Theme-aware shimmer placeholder. Use to mark loading states for cards,
 * rows, charts, etc. while data is being fetched.
 *
 *   <Skeleton className="h-4 w-32" />
 *   <Skeleton className="h-64 w-full rounded-md" />
 */
export function Skeleton({ className = "", style, ...rest }) {
  return (
    <div
      className={`ledger-skeleton ${className}`}
      style={style}
      aria-hidden="true"
      {...rest}
    />
  );
}

/**
 * Convenience row of N stacked skeleton lines, useful inside cards.
 */
export function SkeletonLines({ count = 3, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === count - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

export default Skeleton;
