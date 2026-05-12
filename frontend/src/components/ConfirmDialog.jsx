import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Button } from "./ui/button";

/**
 * Promise-based confirm dialog.
 *
 * Replacement for `window.confirm` which is unreliable inside packaged
 * Electron apps (Chromium disables native dialog popups by default and
 * returns undefined immediately, silently breaking delete actions).
 *
 * Usage:
 *   const confirm = useConfirm();
 *   if (!(await confirm({ title: "Delete?", body: "..." }))) return;
 */

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [state, setState] = useState({
    open: false,
    title: "",
    body: "",
    confirmLabel: "Delete",
    destructive: true,
  });
  const resolverRef = useRef(null);

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setState({
        open: true,
        title: opts.title || "Are you sure?",
        body: opts.body || "",
        confirmLabel: opts.confirmLabel || "Delete",
        cancelLabel: opts.cancelLabel || "Cancel",
        destructive: opts.destructive !== false,
      });
    });
  }, []);

  const close = (result) => {
    setState((s) => ({ ...s, open: false }));
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
  };

  // Defensive: Radix Dialog/DropdownMenu sometimes leak `body { pointer-events: none }`
  // when a dialog is opened on top of another closing portal (typical when
  // confirm() is triggered from inside a DropdownMenuItem). Strip any leaked
  // inline style every time our confirm dialog closes so the next interaction
  // isn't silently blocked.
  useEffect(() => {
    if (!state.open) {
      const t = setTimeout(() => {
        if (document.body.style.pointerEvents === "none") {
          document.body.style.pointerEvents = "";
        }
      }, 200);
      return () => clearTimeout(t);
    }
  }, [state.open]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog open={state.open} onOpenChange={(o) => !o && close(false)}>
        <DialogContent className="bg-[var(--c-card)] border-[var(--c-border)]" data-testid="confirm-dialog">
          <DialogHeader>
            <DialogTitle style={{ fontFamily: "Work Sans" }}>{state.title}</DialogTitle>
            {state.body && (
              <DialogDescription className="text-[var(--c-muted)] whitespace-pre-line">
                {state.body}
              </DialogDescription>
            )}
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => close(false)}
              data-testid="confirm-cancel-btn"
              className="border-[var(--c-border)]"
            >
              {state.cancelLabel}
            </Button>
            <Button
              onClick={() => close(true)}
              data-testid="confirm-ok-btn"
              className={
                state.destructive
                  ? "bg-[var(--c-danger)] hover:bg-[var(--c-danger-deep)] text-[var(--c-on-primary)]"
                  : "bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]"
              }
              autoFocus
            >
              {state.confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    // Safe default: if the provider is missing, refuse the action rather than
    // silently confirming destructive operations.
    return async () => false;
  }
  return ctx;
}
