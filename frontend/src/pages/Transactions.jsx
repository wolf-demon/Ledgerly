import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useProject } from "../lib/projectContext";
import api, { formatGBP } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Tag, Search, Trash2, Sparkles, Upload as UploadIcon } from "lucide-react";
import CategorizeDialog from "../components/CategorizeDialog";
import { toast } from "sonner";

export default function Transactions() {
  const { active } = useProject();
  const [params] = useSearchParams();
  const initialFilter = params.get("filter") || "all";

  const [filter, setFilter] = useState(initialFilter);
  const [search, setSearch] = useState("");
  const [transactions, setTransactions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (!active) return;
    setLoading(true);
    try {
      const params = { project_id: active.id, limit: 5000 };
      if (filter === "uncategorized") params.uncategorized = true;
      const [t, c] = await Promise.all([
        api.get("/transactions", { params }),
        api.get("/categories", { params: { project_id: active.id } }),
      ]);
      setTransactions(t.data);
      setCategories(c.data);
    } finally {
      setLoading(false);
    }
  }, [active, filter]);

  useEffect(() => {
    load();
  }, [load]);

  if (!active) {
    return <div className="text-[#656C5A]">Create or select a project first.</div>;
  }

  const catMap = Object.fromEntries(categories.map((c) => [c.id, c]));
  const filtered = transactions.filter((t) =>
    !search ? true : t.description.toLowerCase().includes(search.toLowerCase())
  );

  const remove = async (id) => {
    if (!window.confirm("Delete this transaction?")) return;
    await api.delete(`/transactions/${id}`);
    toast.success("Deleted");
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Ledger</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
          Transactions
        </h1>
      </div>

      <Card className="p-4 bg-white border-[#EAE3D9] shadow-none">
        <div className="flex flex-wrap gap-3 items-center justify-between">
          <div className="flex items-center gap-2">
            {[
              { k: "all", label: "All" },
              { k: "uncategorized", label: "Uncategorized" },
            ].map((b) => (
              <button
                key={b.k}
                data-testid={`filter-${b.k}`}
                onClick={() => setFilter(b.k)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  filter === b.k ? "bg-[#364C2E] text-white" : "bg-[#F4EBE1] text-[#1F2E1B] hover:bg-[#EAE3D9]"
                }`}
              >
                {b.label}
              </button>
            ))}
          </div>
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#656C5A]" />
            <Input
              data-testid="tx-search"
              placeholder="Search description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-white border-[#EAE3D9]"
            />
          </div>
        </div>
      </Card>

      <Card className="bg-white border-[#EAE3D9] shadow-none overflow-hidden">
        {loading ? (
          <div className="p-8 text-[#656C5A]">Loading transactions...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-[#656C5A]">No transactions{filter === "uncategorized" ? " need categorizing 🎉" : " yet"}.</p>
            <Link to="/upload">
              <Button className="mt-4 bg-[#364C2E] hover:bg-[#22331D] text-white" data-testid="empty-upload-btn">
                <UploadIcon className="w-4 h-4 mr-2" /> Upload statement
              </Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="transactions-table">
              <thead>
                <tr className="text-left text-[#656C5A] border-b border-[#EAE3D9]">
                  <th className="py-3 px-4 font-medium">Date</th>
                  <th className="py-3 px-4 font-medium">Description</th>
                  <th className="py-3 px-4 font-medium">Category</th>
                  <th className="py-3 px-4 font-medium text-right">Amount</th>
                  <th className="py-3 px-4 font-medium text-right w-32">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => {
                  const cat = catMap[t.category_id];
                  return (
                    <tr key={t.id} className="border-b border-[#EAE3D9]/50 hover:bg-[#F4EBE1]/30 transition-colors">
                      <td className="py-3 px-4 text-[#656C5A] whitespace-nowrap">{t.date}</td>
                      <td className="py-3 px-4 max-w-md truncate" title={t.description}>{t.description}</td>
                      <td className="py-3 px-4">
                        {cat ? (
                          <span
                            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                            style={{ backgroundColor: `${cat.color}1A`, color: cat.color }}
                          >
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: cat.color }} />
                            {cat.name}
                          </span>
                        ) : (
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-[#F4EBE1] text-[#656C5A]">
                            Uncategorized
                          </span>
                        )}
                      </td>
                      <td className={`py-3 px-4 text-right font-medium whitespace-nowrap ${t.amount >= 0 ? "text-[#4B6B40]" : "text-[#D96C4E]"}`}>
                        {formatGBP(t.amount)}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            data-testid={`categorize-btn-${t.id}`}
                            onClick={() => { setEditing(t); setOpen(true); }}
                            className="hover:bg-[#F4EBE1]"
                          >
                            <Tag className="w-4 h-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            data-testid={`delete-tx-btn-${t.id}`}
                            onClick={() => remove(t.id)}
                            className="hover:bg-[#D96C4E]/10 text-[#D96C4E]"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CategorizeDialog
        open={open}
        onOpenChange={setOpen}
        transaction={editing}
        categories={categories}
        projectId={active.id}
        onSaved={load}
      />

      <p className="text-xs text-[#656C5A] flex items-center gap-1.5">
        <Sparkles className="w-3.5 h-3.5" /> Tip: when you categorize a transaction, enable "Remember for similar" to auto-classify future imports.
      </p>
    </div>
  );
}
