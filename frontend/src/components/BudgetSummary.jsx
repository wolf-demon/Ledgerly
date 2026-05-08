import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatGBP } from "../lib/api";
import { Card } from "../components/ui/card";
import { Wallet, ArrowRight } from "lucide-react";

const STATUS = {
  ok: "bg-[#4B6B40]",
  warn: "bg-[#D1A77E]",
  over: "bg-[#D96C4E]",
};

export default function BudgetSummary({ projectId, year, month }) {
  const [items, setItems] = useState(null);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get("/budgets/progress", {
          params: { project_id: projectId, year, month },
        });
        if (!cancelled) setItems(r.data.items || []);
      } catch {
        if (!cancelled) setItems([]);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, year, month]);

  if (items === null) return null;

  if (items.length === 0) {
    return (
      <Card className="p-6 bg-white border-[#EAE3D9] shadow-none" data-testid="dashboard-budget-empty">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Wallet className="w-4 h-4 text-[#364C2E]" />
              <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Budgets</h3>
            </div>
            <p className="text-sm text-[#656C5A] mt-2">
              Set a monthly cap per category to track your spending against a target.
            </p>
          </div>
          <Link
            to="/budgets"
            className="text-sm text-[#364C2E] flex items-center gap-1 hover:underline"
            data-testid="dashboard-budget-cta"
          >
            Set budgets <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </Card>
    );
  }

  const sorted = [...items].sort((a, b) => b.percent - a.percent);
  const top = sorted.slice(0, 5);
  const overCount = items.filter((i) => i.status === "over").length;
  const onTrack = items.filter((i) => i.status === "ok").length;

  return (
    <Card className="p-6 bg-white border-[#EAE3D9] shadow-none" data-testid="dashboard-budget-summary">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <Wallet className="w-4 h-4 text-[#364C2E]" />
            <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Budgets</h3>
          </div>
          <p className="text-xs text-[#656C5A] mt-0.5">
            {onTrack} on track · {overCount > 0 ? `${overCount} over` : "all under cap"}
          </p>
        </div>
        <Link
          to="/budgets"
          className="text-sm text-[#364C2E] flex items-center gap-1 hover:underline"
          data-testid="dashboard-budget-manage"
        >
          Manage <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      <div className="space-y-3">
        {top.map((p) => {
          const width = Math.min(100, p.percent);
          return (
            <div key={p.id} data-testid={`dashboard-budget-row-${p.category_id}`}>
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: p.category_color }} />
                  <span className="truncate text-[#1F2E1B]">{p.category_name}</span>
                </div>
                <span className="text-xs text-[#656C5A] tabular-nums">
                  {formatGBP(p.spent)} / {formatGBP(p.effective_amount)}
                </span>
              </div>
              <div className="h-1.5 bg-[#EAE3D9] rounded-full mt-1.5 overflow-hidden">
                <div
                  className={`h-full ${STATUS[p.status]} transition-all duration-500`}
                  style={{ width: `${width}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
