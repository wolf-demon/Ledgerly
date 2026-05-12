import React, { useState, useEffect, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { Sparkles, Loader2 } from "lucide-react";
import api, { formatGBP } from "../lib/api";
import { toast } from "sonner";

export default function CategorizeDialog({ open, onOpenChange, transaction, categories, projectId, onSaved }) {
  const [selected, setSelected] = useState("");
  const [applyToSimilar, setApplyToSimilar] = useState(true);
  const [suggestion, setSuggestion] = useState(null);
  const [loadingSuggest, setLoadingSuggest] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchSuggestion = useCallback(async () => {
    if (!transaction) return;
    setLoadingSuggest(true);
    setSuggestion(null);
    try {
      const res = await api.post("/categorize/suggest", {
        project_id: projectId,
        description: transaction.description,
        amount: transaction.amount,
      });
      setSuggestion(res.data);
      if (res.data?.suggested_category_id && !selected) {
        setSelected(res.data.suggested_category_id);
      }
    } catch {
      // silent
    } finally {
      setLoadingSuggest(false);
    }
  }, [transaction, projectId, selected]);

  useEffect(() => {
    if (open && transaction) {
      setSelected(transaction.category_id || "");
      setApplyToSimilar(true);
      setSuggestion(null);
    }
  }, [open, transaction]);

  const save = async () => {
    if (!selected) {
      toast.error("Pick a category");
      return;
    }
    setSaving(true);
    try {
      const res = await api.put(`/transactions/${transaction.id}`, {
        category_id: selected,
        apply_to_similar: applyToSimilar,
      });
      const extra = res.data?.affected_similar || 0;
      toast.success(extra > 0 ? `Saved & applied to ${extra} similar transactions` : "Saved");
      onOpenChange(false);
      onSaved?.();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!transaction) return null;

  const isIncome = transaction.amount >= 0;
  const filteredCats = categories.filter((c) => c.type === (isIncome ? "income" : "expense"));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[var(--c-card)] border-[var(--c-border)] max-w-lg">
        <DialogHeader>
          <DialogTitle style={{ fontFamily: "Work Sans" }}>Categorize transaction</DialogTitle>
          <DialogDescription className="text-[var(--c-muted)]">
            Assign a category. Optionally apply to all similar transactions and remember the rule.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="rounded-md bg-[color-mix(in_srgb,var(--c-surface)_50%,transparent)] border border-[var(--c-border)] p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">Transaction</div>
            <div className="mt-1 font-medium" data-testid="categorize-tx-description">{transaction.description}</div>
            <div className="flex items-center justify-between mt-2 text-sm">
              <span className="text-[var(--c-muted)]">{transaction.date}</span>
              <span className={isIncome ? "text-[var(--c-success)] font-semibold" : "text-[var(--c-danger)] font-semibold"}>
                {formatGBP(transaction.amount)}
              </span>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            onClick={fetchSuggestion}
            disabled={loadingSuggest}
            data-testid="ai-suggest-btn"
            className="w-full border-[var(--c-border)] hover:bg-[var(--c-surface)]"
          >
            {loadingSuggest ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4 mr-2 text-[var(--c-primary)]" />
            )}
            {loadingSuggest ? "Thinking..." : "Suggest with AI"}
          </Button>

          {suggestion && (
            <div className="rounded-md border border-[color-mix(in_srgb,var(--c-accent)_40%,transparent)] bg-[var(--c-bg)] p-3 text-sm" data-testid="ai-suggestion-panel">
              {suggestion.suggested_name ? (
                <>
                  <div className="font-medium">
                    AI suggests: <span className="text-[var(--c-primary)]">{suggestion.suggested_name}</span>
                  </div>
                  {suggestion.reason && (
                    <div className="text-[var(--c-muted)] mt-1 text-xs">{suggestion.reason}</div>
                  )}
                </>
              ) : (
                <div className="text-[var(--c-muted)]">
                  AI couldn’t pick a confident match. {suggestion.reason}
                </div>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label>Category ({isIncome ? "income" : "expense"})</Label>
            <div className="grid grid-cols-2 gap-2 max-h-56 overflow-auto scrollbar-thin pr-1">
              {filteredCats.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelected(c.id)}
                  data-testid={`category-pick-${c.id}`}
                  className={`text-left px-3 py-2 rounded-md border text-sm transition-all ${
                    selected === c.id
                      ? "border-[var(--c-primary)] bg-[var(--c-primary)] text-[var(--c-on-primary)]"
                      : "border-[var(--c-border)] hover:border-[var(--c-accent)]"
                  }`}
                >
                  <span className="inline-block w-2.5 h-2.5 rounded-full mr-2" style={{ backgroundColor: c.color }} />
                  {c.name}
                </button>
              ))}
              {filteredCats.length === 0 && (
                <div className="col-span-2 text-sm text-[var(--c-muted)]">
                  No {isIncome ? "income" : "expense"} categories yet. Create one in Categories.
                </div>
              )}
            </div>
          </div>

          <label className="flex items-start gap-2 cursor-pointer">
            <Checkbox
              checked={applyToSimilar}
              onCheckedChange={(v) => setApplyToSimilar(!!v)}
              data-testid="apply-to-similar-checkbox"
            />
            <div className="text-sm">
              <div>Remember this for similar transactions</div>
              <div className="text-xs text-[var(--c-muted)]">
                Future and existing transactions matching this merchant will be auto-categorized.
              </div>
            </div>
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cancel-categorize-btn">
            Cancel
          </Button>
          <Button
            onClick={save}
            disabled={saving}
            data-testid="save-categorize-btn"
            className="bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]"
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
