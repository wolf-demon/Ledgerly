import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useProject } from "../lib/projectContext";
import { useBankAccount } from "../lib/bankAccountContext";
import api, { formatGBP, API } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Checkbox } from "../components/ui/checkbox";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "../components/ui/dropdown-menu";
import { Tag, Search, Trash2, Sparkles, Upload as UploadIcon, Download, Wand2, X, RefreshCw, Bot, Loader2, Scissors, ChevronDown, ChevronRight } from "lucide-react";
import CategorizeDialog from "../components/CategorizeDialog";
import SplitDialog from "../components/SplitDialog";
import SplitReviewDialog from "../components/SplitReviewDialog";
import { useConfirm } from "../components/ConfirmDialog";
import { useFetchGuard } from "../lib/useFetchGuard";
import { toast } from "sonner";

// Convert an ISO date "YYYY-MM-DD" into a JS Date with no timezone surprise.
function toDate(iso) { return new Date(iso + "T00:00:00"); }

// Return "YYYY-Www" for the ISO week the date belongs to. Used for the
// week-grouping mode.
function isoWeek(d) {
  const date = new Date(d.valueOf());
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7));
  const week1 = new Date(date.getFullYear(), 0, 4);
  const num = 1 + Math.round(((date - week1) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  return `${date.getFullYear()}-W${String(num).padStart(2, "0")}`;
}

function groupKey(t, mode) {
  if (mode === "flat") return null;
  const d = toDate(t.date);
  if (mode === "day") return t.date;
  if (mode === "week") return isoWeek(d);
  if (mode === "month") return t.date.slice(0, 7);
  return null;
}

function groupLabel(key, mode) {
  if (mode === "day") {
    return toDate(key).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  }
  if (mode === "week") {
    return `Week ${key.split("-W")[1]}, ${key.split("-W")[0]}`;
  }
  if (mode === "month") {
    const [y, m] = key.split("-");
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }
  return key;
}

export default function Transactions() {
  const { active, revision, bumpRevision } = useProject();
  const { accounts, selectedId: bankAccountId } = useBankAccount();
  const confirm = useConfirm();
  const guard = useFetchGuard();
  const [params] = useSearchParams();
  const initialFilter = params.get("filter") || "all";

  const [filter, setFilter] = useState(initialFilter);
  const [search, setSearch] = useState("");
  const [groupMode, setGroupMode] = useState("flat"); // flat | day | week | month
  const [transactions, setTransactions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [splitChildrenByParent, setSplitChildrenByParent] = useState({});
  const [showSplitParents, setShowSplitParents] = useState(false);
  const [expandedParents, setExpandedParents] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [splitTarget, setSplitTarget] = useState(null);
  const [splitOpen, setSplitOpen] = useState(false);
  const [aiSplitOpen, setAiSplitOpen] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkApplyRule, setBulkApplyRule] = useState(true);
  const [autoBusy, setAutoBusy] = useState(false);

  const accountMap = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a])), [accounts]);

  const load = useCallback(async () => {
    if (!active) {
      // Clear stale data immediately when there is no active project so we
      // don't render the previous project's transactions during the switch.
      setTransactions([]);
      setCategories([]);
      setSplitChildrenByParent({});
      return;
    }
    setLoading(true);
    guard(async ({ isStale }) => {
      try {
        const params = { project_id: active.id, limit: 5000, include_split_parents: showSplitParents };
        if (filter === "uncategorized") params.uncategorized = true;
        if (bankAccountId) params.bank_account_id = bankAccountId;
        const [t, c] = await Promise.all([
          api.get("/transactions", { params }),
          api.get("/categories", { params: { project_id: active.id } }),
        ]);
        if (isStale()) return;
        setTransactions(t.data);
        setCategories(c.data);
        setSelected(new Set());

        // Build a quick "split parent id -> [children]" map for indenting.
        const map = {};
        for (const tx of t.data) {
          const pid = tx.parent_transaction_id;
          if (pid) {
            if (!map[pid]) map[pid] = [];
            map[pid].push(tx);
          }
        }
        setSplitChildrenByParent(map);
      } finally {
        if (!isStale()) setLoading(false);
      }
    });
  }, [active, filter, bankAccountId, showSplitParents, guard]);

  useEffect(() => {
    load();
    // `revision` participates so a global "data has changed" bump forces reload.
  }, [load, revision]);

  const catMap = useMemo(() => Object.fromEntries(categories.map((c) => [c.id, c])), [categories]);
  const filtered = useMemo(
    () => transactions.filter((t) => (!search ? true : t.description.toLowerCase().includes(search.toLowerCase()))),
    [transactions, search],
  );

  // Build [{ key, label, rows, net }] for the chosen group mode.
  const groups = useMemo(() => {
    if (groupMode === "flat") return [{ key: "__all__", label: null, rows: filtered, net: 0 }];
    const map = new Map();
    for (const t of filtered) {
      const k = groupKey(t, groupMode);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(t);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => (a < b ? 1 : -1))
      .map(([key, rows]) => ({
        key,
        label: groupLabel(key, groupMode),
        rows,
        net: rows.reduce((s, t) => s + Number(t.amount), 0),
      }));
  }, [filtered, groupMode]);

  if (!active) {
    return <div className="text-[var(--c-muted)]">Create or select a project first.</div>;
  }

  const allSelected = filtered.length > 0 && filtered.every((t) => selected.has(t.id));
  const someSelected = selected.size > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((t) => t.id)));
    }
  };

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const remove = async (id) => {
    if (!(await confirm({ title: "Delete this transaction?", body: "This cannot be undone." }))) return;
    // Optimistic: drop from local state immediately so the row disappears even
    // before the server round-trip completes.
    const snapshot = transactions;
    setTransactions((prev) => prev.filter((t) => t.id !== id));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    try {
      await api.delete(`/transactions/${id}`);
      toast.success("Deleted");
    } catch (e) {
      // Roll back on failure.
      setTransactions(snapshot);
      toast.error(e?.response?.data?.detail || "Could not delete");
    }
    // Re-sync with the server so totals, split rollups, etc. are correct.
    bumpRevision();
    load();
  };

  const startSplit = (t) => {
    setSplitTarget(t);
    setSplitOpen(true);
  };

  const unsplit = async (t) => {
    if (!(await confirm({
      title: "Remove split?",
      body: "All child split lines will be deleted and the original transaction will reappear in your totals.",
      destructive: true,
    }))) return;
    try {
      await api.delete(`/transactions/${t.id}/split`);
      toast.success("Split removed");
      bumpRevision();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not un-split");
    }
  };

  const toggleParentExpanded = (id) => {
    const next = new Set(expandedParents);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpandedParents(next);
  };

  const bulkCategorize = async (categoryId) => {
    if (selected.size === 0) return;
    try {
      const res = await api.post("/transactions/bulk-categorize", {
        transaction_ids: Array.from(selected),
        category_id: categoryId,
        apply_to_similar: bulkApplyRule,
      });
      const extra = res.data.similar_applied || 0;
      toast.success(
        `Categorized ${res.data.updated} transactions${extra ? ` and ${extra} similar` : ""}`
      );
      bumpRevision();
      load();
    } catch {
      toast.error("Bulk categorize failed");
    }
  };

  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!(await confirm({
      title: `Delete ${selected.size} selected transactions?`,
      body: "This cannot be undone.",
      destructive: true,
    }))) return;
    const ids = Array.from(selected);
    const snapshot = transactions;
    setTransactions((prev) => prev.filter((t) => !selected.has(t.id)));
    setSelected(new Set());
    try {
      await Promise.all(ids.map((id) => api.delete(`/transactions/${id}`)));
      toast.success(`Deleted ${ids.length} transactions`);
    } catch {
      setTransactions(snapshot);
      toast.error("Bulk delete failed");
    }
    bumpRevision();
    load();
  };

  const exportCSV = () => {
    const url = `${API}/transactions/export?project_id=${active.id}`;
    window.open(url, "_blank");
  };

  const reclassify = async () => {
    try {
      const res = await api.post(`/transactions/reclassify?project_id=${active.id}`);
      if (res.data.fixed > 0) {
        toast.success(`Re-classified ${res.data.fixed} of ${res.data.checked} transactions`);
      } else {
        toast.success(`All ${res.data.checked} transactions already correctly classified`);
      }
      bumpRevision();
      load();
    } catch {
      toast.error("Reclassify failed");
    }
  };

  const autoCategorize = async () => {
    const uncategorized = transactions.filter((t) => !t.category_id).length;
    if (uncategorized === 0) {
      toast.success("Nothing to categorize 🎉");
      return;
    }
    if (!(await confirm({
      title: `Auto-categorize ${uncategorized} transactions with AI?`,
      body: "This may create new categories if none of the existing ones fit. Make sure your AI provider is configured in Settings.",
      confirmLabel: "Run AI",
      destructive: false,
    }))) return;
    setAutoBusy(true);
    try {
      const res = await api.post("/transactions/bulk-suggest", {
        project_id: active.id,
        only_uncategorized: true,
        allow_create: true,
        max_items: 500,
      });
      const created = res.data.created_categories?.length || 0;
      const errs = res.data.errors?.length || 0;
      let msg = `Categorized ${res.data.categorized} of ${res.data.processed} transactions`;
      if (created > 0) msg += ` and created ${created} new categor${created === 1 ? "y" : "ies"}`;
      if (errs > 0) msg += ` (${errs} errors)`;
      toast.success(msg);
      bumpRevision();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Auto-categorize failed");
    } finally {
      setAutoBusy(false);
    }
  };

  const renderRow = (t, opts = {}) => {
    const { indent = false } = opts;
    const cat = catMap[t.category_id];
    const acct = t.bank_account_id ? accountMap[t.bank_account_id] : null;
    const isSel = selected.has(t.id);
    const showTime = t.time && t.time !== "00:00:00";
    const isSplitParent = !!t.is_split;
    const children = splitChildrenByParent[t.id] || [];
    const isExpanded = expandedParents.has(t.id);
    return (
      <React.Fragment key={t.id}>
        <tr
          className={`border-b border-[color-mix(in_srgb,var(--c-border)_50%,transparent)] transition-colors ${
            isSel ? "bg-[color-mix(in_srgb,var(--c-surface)_50%,transparent)]" : isSplitParent ? "bg-[color-mix(in_srgb,var(--c-surface)_20%,transparent)] opacity-80" : "hover:bg-[color-mix(in_srgb,var(--c-surface)_30%,transparent)]"
          } ${indent ? "bg-[var(--c-bg-alt)]" : ""}`}
        >
          <td className="py-3 px-4">
            {!indent && (
              <Checkbox checked={isSel} onCheckedChange={() => toggle(t.id)} data-testid={`select-tx-${t.id}`} />
            )}
          </td>
          <td className="py-3 px-4 text-[var(--c-muted)] whitespace-nowrap text-xs">
            <div className="flex items-center gap-1">
              {indent && <span className="text-[var(--c-muted-2)] mr-1">↳</span>}
              {isSplitParent && (
                <button
                  type="button"
                  onClick={() => toggleParentExpanded(t.id)}
                  className="text-[var(--c-muted)] hover:text-[var(--c-ink)]"
                  data-testid={`toggle-split-${t.id}`}
                >
                  {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                </button>
              )}
              <span>{t.date}</span>
            </div>
            {showTime && <div className="text-[10px] opacity-70 tabular-nums ml-3">{t.time.slice(0, 5)}</div>}
          </td>
          <td className="py-3 px-4">
            {acct ? (
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: `${acct.color}1A`, color: acct.color }}
                title={acct.sort_code || ""}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: acct.color }} />
                {acct.name}
              </span>
            ) : (
              <span className="inline-block text-xs text-[var(--c-muted)]">—</span>
            )}
          </td>
          <td className="py-3 px-4 max-w-md truncate" title={t.description}>
            <span className={indent ? "text-sm" : ""}>{t.description}</span>
            {isSplitParent && (
              <span
                className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide bg-[color-mix(in_srgb,var(--c-primary-soft)_15%,transparent)] text-[var(--c-primary-soft)]"
                data-testid={`split-chip-${t.id}`}
              >
                <Scissors className="w-3 h-3" /> Split into {children.length || "…"}
              </span>
            )}
          </td>
          <td className="py-3 px-4">
            {cat ? (
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: `${cat.color}1A`, color: cat.color }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: cat.color }} />
                {cat.name}
              </span>
            ) : isSplitParent ? (
              <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-[color-mix(in_srgb,var(--c-primary-soft)_15%,transparent)] text-[var(--c-primary-soft)]">
                Split parent
              </span>
            ) : (
              <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-[var(--c-surface)] text-[var(--c-muted)]">
                Uncategorized
              </span>
            )}
          </td>
          <td className={`py-3 px-4 text-right font-medium whitespace-nowrap ${
            isSplitParent ? "text-[var(--c-muted)] line-through" : (t.amount >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]")
          }`}>
            {formatGBP(t.amount)}
          </td>
          <td className="py-3 px-4 text-right">
            <div className="flex items-center justify-end gap-1">
              {!isSplitParent && !indent && (
                <Button
                  size="sm" variant="ghost" data-testid={`split-btn-${t.id}`}
                  onClick={() => startSplit(t)}
                  className="hover:bg-[var(--c-surface)]"
                  title="Split into multiple categories"
                >
                  <Scissors className="w-4 h-4" />
                </Button>
              )}
              {isSplitParent && (
                <Button
                  size="sm" variant="ghost" data-testid={`unsplit-btn-${t.id}`}
                  onClick={() => unsplit(t)}
                  className="hover:bg-[color-mix(in_srgb,var(--c-danger)_10%,transparent)] text-[var(--c-danger)]"
                  title="Remove split"
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
              {!isSplitParent && (
                <Button
                  size="sm" variant="ghost" data-testid={`categorize-btn-${t.id}`}
                  onClick={() => { setEditing(t); setOpen(true); }}
                  className="hover:bg-[var(--c-surface)]"
                >
                  <Tag className="w-4 h-4" />
                </Button>
              )}
              <Button
                size="sm" variant="ghost" data-testid={`delete-tx-btn-${t.id}`}
                onClick={() => remove(t.id)}
                className="hover:bg-[color-mix(in_srgb,var(--c-danger)_10%,transparent)] text-[var(--c-danger)]"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </td>
        </tr>
        {/* Inline expansion of a split parent's children when toggled on. */}
        {isSplitParent && isExpanded && children.map((child) => renderRow(child, { indent: true }))}
      </React.Fragment>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Ledger</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Transactions
          </h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            onClick={autoCategorize}
            disabled={autoBusy}
            data-testid="auto-categorize-btn"
            className="bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]"
          >
            {autoBusy ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Categorizing…</>
            ) : (
              <><Bot className="w-4 h-4 mr-2" /> Auto-categorize with AI</>
            )}
          </Button>
          <Button
            onClick={() => setAiSplitOpen(true)}
            data-testid="ai-split-btn"
            variant="outline"
            className="border-[var(--c-border)] hover:bg-[var(--c-surface)]"
            title="Use AI to suggest splits for multi-category transactions"
          >
            <Scissors className="w-4 h-4 mr-2" /> AI: detect splits
          </Button>
          <Button
            onClick={reclassify} variant="outline" data-testid="reclassify-btn"
            className="border-[var(--c-border)] hover:bg-[var(--c-surface)]"
            title="Recompute income/expense type from each transaction's amount sign"
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Re-classify
          </Button>
          <Button onClick={exportCSV} variant="outline" data-testid="export-csv-btn" className="border-[var(--c-border)] hover:bg-[var(--c-surface)]">
            <Download className="w-4 h-4 mr-2" /> Export CSV
          </Button>
        </div>
      </div>

      <Card className="p-4 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
        <div className="flex flex-wrap gap-3 items-center justify-between">
          <div className="flex items-center gap-2 flex-wrap">
            {[
              { k: "all", label: "All" },
              { k: "uncategorized", label: "Uncategorized" },
            ].map((b) => (
              <button
                key={b.k} data-testid={`filter-${b.k}`} onClick={() => setFilter(b.k)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  filter === b.k ? "bg-[var(--c-primary)] text-[var(--c-on-primary)]" : "bg-[var(--c-surface)] text-[var(--c-ink)] hover:bg-[var(--c-border)]"
                }`}
              >
                {b.label}
              </button>
            ))}
            <div className="w-px h-5 bg-[var(--c-border)] mx-1" />
            <span className="text-xs uppercase tracking-wide text-[var(--c-muted)]">Group by</span>
            {[
              { k: "flat", label: "None" },
              { k: "day", label: "Day" },
              { k: "week", label: "Week" },
              { k: "month", label: "Month" },
            ].map((b) => (
              <button
                key={b.k} data-testid={`group-${b.k}`} onClick={() => setGroupMode(b.k)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  groupMode === b.k ? "bg-[var(--c-primary)] text-[var(--c-on-primary)]" : "bg-[var(--c-surface)] text-[var(--c-ink)] hover:bg-[var(--c-border)]"
                }`}
              >
                {b.label}
              </button>
            ))}
          </div>
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-muted)]" />
            <Input
              data-testid="tx-search" placeholder="Search description..." value={search}
              onChange={(e) => setSearch(e.target.value)} className="pl-9 bg-[var(--c-card)] border-[var(--c-border)]"
            />
          </div>
        </div>
      </Card>

      {selected.size > 0 && (
        <div
          className="flex flex-wrap items-center gap-3 px-4 py-3 rounded-md bg-[var(--c-primary)] text-[var(--c-on-primary)] sticky top-4 z-10 shadow-lg"
          data-testid="bulk-actions-bar"
        >
          <span className="font-medium">{selected.size} selected</span>
          <span className="text-[var(--c-on-primary)]/40">|</span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" data-testid="bulk-categorize-btn" className="bg-[var(--c-card)]/15 hover:bg-[var(--c-card)]/25 text-[var(--c-on-primary)] border-0">
                <Wand2 className="w-4 h-4 mr-1.5" /> Categorize as...
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="max-h-80 overflow-auto">
              <DropdownMenuLabel>Income</DropdownMenuLabel>
              {categories.filter((c) => c.type === "income").map((c) => (
                <DropdownMenuItem key={c.id} data-testid={`bulk-cat-${c.id}`} onClick={() => bulkCategorize(c.id)}>
                  <span className="w-2.5 h-2.5 rounded-full mr-2" style={{ backgroundColor: c.color }} />
                  {c.name}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Expense</DropdownMenuLabel>
              {categories.filter((c) => c.type === "expense").map((c) => (
                <DropdownMenuItem key={c.id} data-testid={`bulk-cat-${c.id}`} onClick={() => bulkCategorize(c.id)}>
                  <span className="w-2.5 h-2.5 rounded-full mr-2" style={{ backgroundColor: c.color }} />
                  {c.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <label className="flex items-center gap-2 text-xs cursor-pointer ml-1">
            <Checkbox
              checked={bulkApplyRule} onCheckedChange={(v) => setBulkApplyRule(!!v)} data-testid="bulk-apply-rule"
              className="border-white/40 data-[state=checked]:bg-[var(--c-card)] data-[state=checked]:text-[var(--c-primary)]"
            />
            Remember rule for similar
          </label>
          <Button size="sm" onClick={bulkDelete} data-testid="bulk-delete-btn" className="bg-[var(--c-danger)] hover:bg-[var(--c-danger-deep)] text-[var(--c-on-primary)] ml-auto">
            <Trash2 className="w-4 h-4 mr-1.5" /> Delete
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())} data-testid="bulk-clear-btn"
            className="text-[var(--c-on-primary)]/80 hover:bg-[var(--c-card)]/10 hover:text-[var(--c-on-primary)]">
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}

      <Card className="bg-[var(--c-card)] border-[var(--c-border)] shadow-none overflow-hidden">
        {loading ? (
          <div className="p-8 text-[var(--c-muted)]">Loading transactions...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-[var(--c-muted)]">No transactions{filter === "uncategorized" ? " need categorizing 🎉" : " yet"}.</p>
            <Link to="/upload">
              <Button className="mt-4 bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]" data-testid="empty-upload-btn">
                <UploadIcon className="w-4 h-4 mr-2" /> Upload statement
              </Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="transactions-table">
              <thead>
                <tr className="text-left text-[var(--c-muted)] border-b border-[var(--c-border)]">
                  <th className="py-3 px-4 w-10">
                    <Checkbox checked={allSelected || (someSelected ? "indeterminate" : false)} onCheckedChange={toggleAll} data-testid="select-all-checkbox" />
                  </th>
                  <th className="py-3 px-4 font-medium">Date / Time</th>
                  <th className="py-3 px-4 font-medium">Account</th>
                  <th className="py-3 px-4 font-medium">Description</th>
                  <th className="py-3 px-4 font-medium">Category</th>
                  <th className="py-3 px-4 font-medium text-right">Amount</th>
                  <th className="py-3 px-4 font-medium text-right w-32">Actions</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <React.Fragment key={g.key}>
                    {g.label && (
                      <tr className="bg-[color-mix(in_srgb,var(--c-surface)_40%,transparent)]">
                        <td colSpan={7} className="px-4 py-2 text-xs uppercase tracking-wide text-[var(--c-ink)] flex items-center justify-between">
                          <span className="font-semibold">{g.label}</span>
                          <span className="text-[var(--c-muted)] normal-case tracking-normal pl-4">
                            {g.rows.length} {g.rows.length === 1 ? "tx" : "txs"} · net{" "}
                            <span className={g.net >= 0 ? "text-[var(--c-success)] font-medium" : "text-[var(--c-danger)] font-medium"}>
                              {formatGBP(g.net)}
                            </span>
                          </span>
                        </td>
                      </tr>
                    )}
                    {g.rows.map(renderRow)}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CategorizeDialog
        open={open} onOpenChange={setOpen} transaction={editing}
        categories={categories} projectId={active.id}
        onSaved={() => { bumpRevision(); load(); }}
      />

      <SplitDialog
        open={splitOpen} onOpenChange={setSplitOpen} transaction={splitTarget}
        categories={categories}
        onSaved={() => { bumpRevision(); load(); }}
      />

      <SplitReviewDialog
        open={aiSplitOpen} onOpenChange={setAiSplitOpen}
        projectId={active.id} categories={categories}
        onSaved={() => { bumpRevision(); load(); }}
      />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-[var(--c-muted)] flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" /> Tip: split, categorize, group — and use the AI buttons to do it in bulk.
        </p>
        <label className="text-xs text-[var(--c-muted)] flex items-center gap-2 cursor-pointer">
          <Checkbox
            checked={showSplitParents}
            onCheckedChange={(v) => setShowSplitParents(!!v)}
            data-testid="show-split-parents-toggle"
          />
          Show split parent rows
        </label>
      </div>
    </div>
  );
}
