import React, { useEffect, useMemo, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Plus, Trash2, Wand2, Check, X } from "lucide-react";
import api, { formatGBP } from "../lib/api";
import { toast } from "sonner";

/**
 * Split a single transaction into multiple child rows. Each row picks a
 * category and an amount; the dialog tracks the running "remaining" balance
 * and only enables Save when it hits zero.
 *
 * `initialSplits` (optional) pre-fills the lines — used by the AI suggestion
 * flow to drop in suggested splits for the user to confirm/edit/skip.
 */
export default function SplitDialog({ open, onOpenChange, transaction, categories, onSaved, initialSplits }) {
  const [lines, setLines] = useState([]);

  const expenseCats = useMemo(() => categories.filter((c) => c.type === "expense"), [categories]);
  const incomeCats = useMemo(() => categories.filter((c) => c.type === "income"), [categories]);
  const isIncome = transaction && Number(transaction.amount) >= 0;
  const pool = isIncome ? incomeCats : expenseCats;
  const sign = isIncome ? 1 : -1;

  useEffect(() => {
    if (!open || !transaction) return;
    if (initialSplits && initialSplits.length) {
      // Normalise signs to match the parent.
      setLines(
        initialSplits.map((s) => ({
          amount: Math.abs(Number(s.amount)) * sign,
          category_id: s.category_id || "",
          description: s.description || "",
          reason: s.reason || "",
        })),
      );
    } else {
      const half = Number((transaction.amount / 2).toFixed(2));
      const remainder = Number((transaction.amount - half).toFixed(2));
      setLines([
        { amount: half, category_id: "", description: "" },
        { amount: remainder, category_id: "", description: "" },
      ]);
    }
  }, [open, transaction, initialSplits, sign]);

  if (!transaction) return null;

  const total = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const remaining = Number((Number(transaction.amount) - total).toFixed(2));
  const allCategorised = lines.every((l) => l.category_id);
  const canSave = lines.length >= 2 && Math.abs(remaining) < 0.005 && allCategorised;

  const updateLine = (idx, patch) => {
    const next = lines.slice();
    next[idx] = { ...next[idx], ...patch };
    setLines(next);
  };

  const addLine = () => {
    // Insert a new line that takes the current remaining balance, so the user
    // hits "balanced" immediately on a single click.
    setLines([...lines, { amount: remaining || 0, category_id: "", description: "" }]);
  };

  const removeLine = (idx) => {
    if (lines.length <= 2) return;
    const next = lines.slice();
    next.splice(idx, 1);
    setLines(next);
  };

  const balanceTo = (idx) => {
    // Push the entire remaining balance into row `idx`.
    const next = lines.slice();
    next[idx] = { ...next[idx], amount: Number((Number(next[idx].amount || 0) + remaining).toFixed(2)) };
    setLines(next);
  };

  const save = async () => {
    try {
      await api.post(`/transactions/${transaction.id}/split`, { splits: lines });
      toast.success(`Split into ${lines.length} transactions`);
      onOpenChange(false);
      onSaved && onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not split — check amounts and categories");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-[#EAE3D9] max-w-2xl" data-testid="split-dialog">
        <DialogHeader>
          <DialogTitle style={{ fontFamily: "Work Sans" }}>Split transaction</DialogTitle>
        </DialogHeader>

        <div className="space-y-1 py-1">
          <p className="text-sm text-[#656C5A]">
            {transaction.description}
            <span className="ml-2 font-medium text-[#1F2E1B]">{formatGBP(transaction.amount)}</span>
            <span className="ml-2 text-xs">on {transaction.date}</span>
          </p>
        </div>

        <div className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
          {lines.map((l, idx) => (
            <div
              key={idx}
              className="grid grid-cols-12 gap-2 items-end px-2 py-2 rounded-md border border-[#EAE3D9]/60 hover:border-[#D1A77E]/60 transition-colors"
              data-testid={`split-line-${idx}`}
            >
              <div className="col-span-3">
                {idx === 0 && <Label className="text-xs text-[#656C5A]">Amount £</Label>}
                <div className="flex items-center gap-1">
                  <Input
                    type="number" step="0.01" inputMode="decimal"
                    value={l.amount}
                    onChange={(e) => updateLine(idx, { amount: parseFloat(e.target.value) || 0 })}
                    data-testid={`split-amount-${idx}`}
                    className="h-9 text-right tabular-nums"
                  />
                  <button
                    type="button"
                    onClick={() => balanceTo(idx)}
                    title="Set this line to balance the total"
                    className="text-[10px] px-1.5 py-0.5 rounded text-[#364C2E] bg-[#F4EBE1] hover:bg-[#EAE3D9]"
                    data-testid={`split-balance-${idx}`}
                  >
                    =
                  </button>
                </div>
              </div>
              <div className="col-span-4">
                {idx === 0 && <Label className="text-xs text-[#656C5A]">Category</Label>}
                <select
                  value={l.category_id}
                  onChange={(e) => updateLine(idx, { category_id: e.target.value })}
                  data-testid={`split-category-${idx}`}
                  className="w-full h-9 px-2 bg-white border border-[#EAE3D9] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#364C2E]/20"
                >
                  <option value="">— pick —</option>
                  {pool.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-4">
                {idx === 0 && <Label className="text-xs text-[#656C5A]">Description (optional)</Label>}
                <Input
                  value={l.description}
                  onChange={(e) => updateLine(idx, { description: e.target.value })}
                  placeholder={`Split ${idx + 1}`}
                  data-testid={`split-desc-${idx}`}
                  className="h-9"
                />
              </div>
              <div className="col-span-1 flex justify-end">
                {lines.length > 2 && (
                  <Button
                    size="sm" variant="ghost" onClick={() => removeLine(idx)}
                    className="text-[#D96C4E] hover:bg-[#D96C4E]/10"
                    data-testid={`split-remove-${idx}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
              {l.reason && (
                <p className="col-span-12 text-[11px] text-[#728A66] italic flex items-center gap-1">
                  <Wand2 className="w-3 h-3" /> AI suggestion: {l.reason}
                </p>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between pt-2">
          <Button
            type="button" variant="outline" onClick={addLine}
            className="border-[#EAE3D9] hover:bg-[#F4EBE1]"
            data-testid="split-add-line"
          >
            <Plus className="w-4 h-4 mr-1.5" /> Add line
          </Button>
          <div
            className={`text-sm tabular-nums px-3 py-1.5 rounded-md font-medium ${
              Math.abs(remaining) < 0.005
                ? "bg-[#4B6B40]/10 text-[#4B6B40]"
                : "bg-[#D96C4E]/10 text-[#D96C4E]"
            }`}
            data-testid="split-remaining"
          >
            {Math.abs(remaining) < 0.005 ? (
              <span className="flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Balanced</span>
            ) : (
              <>Remaining: {formatGBP(remaining)}</>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="split-cancel">Cancel</Button>
          <Button
            onClick={save} disabled={!canSave} data-testid="split-save"
            className="bg-[#364C2E] hover:bg-[#22331D] text-white disabled:opacity-50"
          >
            Save split
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
