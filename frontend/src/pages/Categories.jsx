import React, { useEffect, useState, useCallback } from "react";
import { useProject } from "../lib/projectContext";
import { useConfirm } from "../components/ConfirmDialog";
import api from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Plus, Trash2, Edit3 } from "lucide-react";
import { toast } from "sonner";

const PALETTE = ["#364C2E", "#4B6B40", "#728A66", "#D96C4E", "#D1A77E", "#E3C8AA", "#8B5E3C", "#9E7B58"];

export default function Categories() {
  const { active } = useProject();
  const confirm = useConfirm();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", type: "expense", color: PALETTE[0] });

  const load = useCallback(async () => {
    if (!active) return;
    const res = await api.get("/categories", { params: { project_id: active.id } });
    setItems(res.data);
  }, [active]);

  useEffect(() => {
    load();
  }, [load]);

  if (!active) return <div className="text-[#656C5A]">Create or select a project first.</div>;

  const openNew = () => {
    setEditing(null);
    setForm({ name: "", type: "expense", color: PALETTE[0] });
    setOpen(true);
  };

  const openEdit = (c) => {
    setEditing(c);
    setForm({ name: c.name, type: c.type, color: c.color });
    setOpen(true);
  };

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Name required");
      return;
    }
    try {
      if (editing) {
        await api.put(`/categories/${editing.id}`, form);
        toast.success("Updated");
      } else {
        await api.post("/categories", { ...form, project_id: active.id });
        toast.success("Created");
      }
      setOpen(false);
      load();
    } catch {
      toast.error("Failed to save");
    }
  };

  const remove = async (c) => {
    const ok = await confirm({
      title: `Delete category "${c.name}"?`,
      body: "Transactions assigned to this category will become uncategorized. This cannot be undone.",
    });
    if (!ok) return;
    await api.delete(`/categories/${c.id}`);
    toast.success("Deleted");
    load();
  };

  const grouped = {
    income: items.filter((c) => c.type === "income"),
    expense: items.filter((c) => c.type === "expense"),
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Organization</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Categories
          </h1>
          <p className="text-[#656C5A] mt-1 text-sm">Group your income and expenses to see clearer insights.</p>
        </div>
        <Button onClick={openNew} data-testid="new-category-btn" className="bg-[#364C2E] hover:bg-[#22331D] text-white">
          <Plus className="w-4 h-4 mr-1.5" /> New category
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {["income", "expense"].map((type) => (
          <Card key={type} className="p-6 bg-white border-[#EAE3D9] shadow-none">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium capitalize" style={{ fontFamily: "Work Sans" }}>{type}</h3>
              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${type === "income" ? "bg-[#4B6B40]/10 text-[#4B6B40]" : "bg-[#D96C4E]/10 text-[#D96C4E]"}`}>
                {grouped[type].length}
              </span>
            </div>
            <div className="space-y-2" data-testid={`categories-list-${type}`}>
              {grouped[type].length === 0 && <p className="text-sm text-[#656C5A]">No categories yet.</p>}
              {grouped[type].map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between px-4 py-3 rounded-md border border-[#EAE3D9]/70 hover:border-[#D1A77E] hover:bg-[#F4EBE1]/30 transition-all"
                  data-testid={`category-row-${c.id}`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: c.color }} />
                    <span className="truncate font-medium">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" onClick={() => openEdit(c)} data-testid={`edit-cat-${c.id}`}>
                      <Edit3 className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(c)} data-testid={`delete-cat-${c.id}`} className="text-[#D96C4E] hover:bg-[#D96C4E]/10">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-white border-[#EAE3D9]">
          <DialogHeader>
            <DialogTitle style={{ fontFamily: "Work Sans" }}>{editing ? "Edit category" : "New category"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                value={form.name}
                data-testid="category-name-input"
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Coffee shops"
              />
            </div>
            <div className="space-y-2">
              <Label>Type</Label>
              <div className="flex gap-2">
                {["income", "expense"].map((t) => (
                  <button
                    key={t}
                    data-testid={`category-type-${t}`}
                    type="button"
                    onClick={() => setForm({ ...form, type: t })}
                    className={`flex-1 px-3 py-2 rounded-md text-sm border transition-colors ${
                      form.type === t ? "bg-[#364C2E] text-white border-[#364C2E]" : "bg-white border-[#EAE3D9] hover:bg-[#F4EBE1]"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label>Color</Label>
              <div className="flex flex-wrap gap-2">
                {PALETTE.map((p) => (
                  <button
                    key={p}
                    type="button"
                    data-testid={`color-${p}`}
                    onClick={() => setForm({ ...form, color: p })}
                    className={`w-8 h-8 rounded-full border-2 transition-all ${form.color === p ? "border-[#1F2E1B] scale-110" : "border-transparent"}`}
                    style={{ backgroundColor: p }}
                    aria-label={`Pick ${p}`}
                  />
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} data-testid="cancel-category-btn">Cancel</Button>
            <Button onClick={save} className="bg-[#364C2E] hover:bg-[#22331D] text-white" data-testid="save-category-btn">
              {editing ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
