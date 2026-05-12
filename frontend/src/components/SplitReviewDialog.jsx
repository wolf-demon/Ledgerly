import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Sparkles, ChevronRight, ChevronLeft, SkipForward, Wand2 } from "lucide-react";
import api, { formatGBP } from "../lib/api";
import { toast } from "sonner";
import SplitDialog from "./SplitDialog";

/**
 * Walks the user through AI-suggested splits one candidate at a time.
 * For each candidate the user must explicitly Confirm or Skip — nothing is
 * applied automatically.
 */
export default function SplitReviewDialog({ open, onOpenChange, projectId, categories, onSaved }) {
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  const [editingSplit, setEditingSplit] = useState(false);
  const [skipped, setSkipped] = useState(0);
  const [applied, setApplied] = useState(0);

  useEffect(() => {
    if (!open || !projectId) return;
    setLoading(true);
    setCandidates([]);
    setIndex(0);
    setApplied(0);
    setSkipped(0);
    (async () => {
      try {
        const r = await api.post("/transactions/detect-splits", {
          project_id: projectId,
          min_amount: 25,
          max_items: 40,
        });
        setCandidates(r.data.candidates || []);
        if ((r.data.candidates || []).length === 0) {
          toast.success("No multi-category transactions detected 👌");
          onOpenChange(false);
        }
      } catch (e) {
        toast.error(e?.response?.data?.detail || "AI split detection failed");
        onOpenChange(false);
      } finally {
        setLoading(false);
      }
    })();
  }, [open, projectId, onOpenChange]);

  const current = candidates[index];
  const total = candidates.length;
  const next = () => setIndex((i) => Math.min(i + 1, total - 1));
  const prev = () => setIndex((i) => Math.max(i - 1, 0));

  const skip = () => {
    setSkipped((s) => s + 1);
    if (index < total - 1) next();
    else finish();
  };

  const finish = () => {
    if (applied || skipped) {
      toast.success(`${applied} applied · ${skipped} skipped`);
    }
    onOpenChange(false);
    onSaved && onSaved();
  };

  const accept = async () => {
    // Strip the AI metadata fields and post the split as-is.
    const splits = current.splits
      .filter((s) => s.category_id) // can only accept lines that mapped to an existing category
      .map((s) => ({
        amount: current.transaction.amount >= 0 ? Math.abs(s.amount) : -Math.abs(s.amount),
        category_id: s.category_id,
        description: undefined,
      }));
    if (splits.length < 2) {
      toast.error("AI suggested categories that don't exist yet — use Edit to pick existing ones.");
      return;
    }
    // Rebalance just in case rounding has crept in after the abs/sign flip.
    const sumNow = splits.reduce((s, l) => s + l.amount, 0);
    const delta = current.transaction.amount - sumNow;
    if (Math.abs(delta) > 0.005) splits[splits.length - 1].amount = Number((splits[splits.length - 1].amount + delta).toFixed(2));
    try {
      await api.post(`/transactions/${current.transaction.id}/split`, { splits });
      setApplied((a) => a + 1);
      toast.success("Split applied");
      if (index < total - 1) next();
      else finish();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not apply split");
    }
  };

  if (!current && !loading) return null;

  return (
    <>
      <Dialog open={open && !editingSplit} onOpenChange={onOpenChange}>
        <DialogContent className="bg-white border-[#EAE3D9] max-w-xl" data-testid="split-review-dialog">
          <DialogHeader>
            <DialogTitle style={{ fontFamily: "Work Sans" }} className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#364C2E]" /> Review AI-suggested splits
            </DialogTitle>
          </DialogHeader>

          {loading ? (
            <div className="py-12 text-center text-[#656C5A]">
              <Wand2 className="w-5 h-5 mx-auto mb-2 animate-pulse" />
              Looking for multi-category transactions…
            </div>
          ) : current ? (
            <div className="space-y-4 py-2">
              <div className="flex items-center justify-between text-xs text-[#656C5A]">
                <span>Candidate {index + 1} of {total}</span>
                <span>
                  {applied} applied · {skipped} skipped
                </span>
              </div>

              <div className="rounded-md border border-[#EAE3D9] bg-[#FAF7F2] px-4 py-3">
                <p className="font-medium text-[#1F2E1B]" data-testid="review-tx-desc">{current.transaction.description}</p>
                <p className="text-sm text-[#656C5A]">
                  {current.transaction.date} ·{" "}
                  <span className={current.transaction.amount >= 0 ? "text-[#4B6B40]" : "text-[#D96C4E]"}>
                    {formatGBP(current.transaction.amount)}
                  </span>
                </p>
                {current.reason && (
                  <p className="text-xs text-[#728A66] mt-2 italic">
                    AI reasoning: {current.reason}
                  </p>
                )}
                {current.auto_balanced && (
                  <p className="text-[10px] uppercase tracking-wide text-[#D1A77E] mt-1" data-testid="review-auto-balanced">
                    Last line auto-balanced for rounding
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <p className="text-xs uppercase tracking-wide text-[#656C5A]">Suggested split</p>
                {current.splits.map((s, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between px-3 py-2 rounded-md border border-[#EAE3D9]/60"
                    data-testid={`review-split-line-${i}`}
                  >
                    <div className="min-w-0">
                      <p className={`text-sm ${s.category_known ? "" : "text-[#D96C4E]"}`}>
                        {s.category_name}
                        {!s.category_known && (
                          <span className="ml-1 text-[10px] uppercase tracking-wide">(new — edit to map)</span>
                        )}
                      </p>
                      {s.reason && <p className="text-xs text-[#728A66] truncate">{s.reason}</p>}
                    </div>
                    <span className="tabular-nums font-medium">{formatGBP(s.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {!loading && current && (
            <DialogFooter className="flex-wrap gap-2">
              <Button
                variant="outline" onClick={prev} disabled={index === 0}
                className="border-[#EAE3D9]"
                data-testid="review-prev"
              >
                <ChevronLeft className="w-4 h-4" /> Prev
              </Button>
              <Button
                variant="outline" onClick={skip}
                className="border-[#EAE3D9]"
                data-testid="review-skip"
              >
                <SkipForward className="w-4 h-4 mr-1.5" /> Skip
              </Button>
              <Button
                variant="outline" onClick={() => setEditingSplit(true)}
                className="border-[#EAE3D9]"
                data-testid="review-edit"
              >
                Edit before applying
              </Button>
              <Button
                onClick={accept}
                disabled={current.splits.filter((s) => s.category_known).length < 2}
                className="bg-[#364C2E] hover:bg-[#22331D] text-white disabled:opacity-50 ml-auto"
                data-testid="review-confirm"
              >
                Confirm split <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {/* "Edit before applying" pops the regular SplitDialog pre-seeded with AI lines */}
      <SplitDialog
        open={editingSplit}
        onOpenChange={(v) => {
          setEditingSplit(v);
          if (!v) {
            // The SplitDialog handles its own save — if it succeeded, advance.
            // (it calls onSaved which we use here to bump applied count)
          }
        }}
        transaction={current?.transaction}
        categories={categories}
        initialSplits={current?.splits}
        onSaved={() => {
          setApplied((a) => a + 1);
          setEditingSplit(false);
          if (index < total - 1) next();
          else finish();
        }}
      />
    </>
  );
}
