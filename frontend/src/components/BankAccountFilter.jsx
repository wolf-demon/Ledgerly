import React, { useState } from "react";
import { useBankAccount } from "../lib/bankAccountContext";
import { Wallet, ChevronDown, Check } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "./ui/dropdown-menu";

/**
 * Header pill that filters the entire app to a single bank account
 * (or "All accounts" to clear). Selection persists across pages and reloads
 * via the BankAccountContext (which stores per-project state in localStorage).
 */
export default function BankAccountFilter() {
  const { accounts, selectedId, setSelectedId, selected } = useBankAccount();
  const [open, setOpen] = useState(false);

  if (!accounts.length) {
    return (
      <div
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[var(--c-surface)] text-[var(--c-muted)] text-xs"
        data-testid="bank-filter-empty"
        title="Upload a statement to create a bank account"
      >
        <Wallet className="w-3.5 h-3.5" />
        No accounts yet
      </div>
    );
  }

  const label = selected ? selected.name : "All accounts";
  const dotColor = selected ? selected.color : "var(--c-primary)";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        data-testid="bank-filter-trigger"
        className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-full bg-[var(--c-card)] border border-[var(--c-border)] hover:border-[var(--c-accent)] text-sm transition-colors"
      >
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: dotColor }} />
        <span className="font-medium text-[var(--c-ink)]">{label}</span>
        <ChevronDown className="w-3.5 h-3.5 text-[var(--c-muted)]" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <DropdownMenuLabel className="text-xs text-[var(--c-muted)] uppercase tracking-wide">Bank account</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={selectedId || "__all__"}
          onValueChange={(v) => setSelectedId(v === "__all__" ? null : v)}
        >
          <DropdownMenuRadioItem value="__all__" data-testid="bank-filter-all">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--c-primary)]" />
              All accounts
            </div>
          </DropdownMenuRadioItem>
          {accounts.map((a) => (
            <DropdownMenuRadioItem key={a.id} value={a.id} data-testid={`bank-filter-${a.id}`}>
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: a.color }} />
                <span className="truncate">{a.name}</span>
                {a.sort_code && (
                  <span className="text-xs text-[var(--c-muted)] ml-auto pl-2">{a.sort_code}</span>
                )}
              </div>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
