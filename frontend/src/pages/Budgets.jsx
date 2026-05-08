import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useProject } from "../lib/projectContext";
import api, { formatGBP, MONTHS } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Switch } from "../components/ui/switch";
import { Wallet, Save, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const STATUS_STYLES = {
  ok: { bar: "bg-[#4B6B40]", text: "text-[#4B6B40]", chip: "bg-[#4B6B40]/10 text-[#4B6B40]" },
  warn: { bar: "bg-[#D1A77E]", text: "text-[#8B5E3C]", chip: "bg-[#D1A77E]/20 text-[#8B5E3C]" },
  over: { bar: "bg-[#D96C4E]", text: "text-[#D96C4E]", chip: "bg-[#D96C4E]/15 text-[#D96C4E]" },
};

function BudgetRow({ category, budget, progress, onChange }) {
  const [amount, setAmount] = useState(budget?.amount?.toString() ?? "");
  const [period, setPeriod] = useState(budget?.period ?? "monthly");
  const [rollover, setRollover] = useState(Boolean(budget?.rollover));
  const [saving, setSaving] = useState(false);

  // Sync local state when the underlying budget changes (project switch, server upsert).
  useEffect(() => {
    setAmount(budget?.amount?.toString() ?? "");
    setPeriod(budget?.period ?? "monthly");
    setRollover(Boolean(budget?.rollover));
  }, [budget?.amount, budget?.period, budget?.rollover]);

  const persist = async () => {
    const numericAmount = parseFloat(amount) || 0;
    setSaving(true);
    try {
      await api.post("/budgets", {
        project_id: category.project_id,
        category_id: category.id,
        period,
        amount: numericAmount,
        rollover,
      });
      toast.success(numericAmount === 0 ? "Budget removed" : "Budget saved");
      onChange();
    } catch (e) {
      toast.error("Could not save budget");
    } finally {
      setSaving(false);
    }
  };

  const status = progress?.status ?? "ok";
  const styles = STATUS_STYLES[status];
  const percent = progress ? Math.min(100, progress.percent) : 0;
  const overflow = progress && progress.percent > 100 ? progress.percent - 100 : 0;

  const verb = category.type === "income" ? "Received" : "Spent";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="grid grid-cols-12 gap-4 items-center py-4 border-b border-[#EAE3D9] last:border-b-0"
      data-testid={`budget-row-${category.id}`}
    >
      <div className="col-span-12 sm:col-span-3 flex items-center gap-2 min-w-0">
        <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: category.color }} />
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{category.name}</div>
          <div className="text-xs text-[#656C5A] capitalize">{category.type}</div>
        </div>
      </div>

      <div className="col-span-6 sm:col-span-2 flex items-center gap-1">
        <span className="text-[#656C5A] text-sm">£</span>
        <Input
          type="number"
          inputMode="decimal"
          step="10"
          min="0"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0"
          data-testid={`budget-amount-${category.id}`}
          className="h-9"
        />
      </div>

      <div className="col-span-6 sm:col-span-2">
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          data-testid={`budget-period-${category.id}`}
          className="w-full h-9 px-3 bg-white border border-[#EAE3D9] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#364C2E]/20"
        >
          <option value="monthly">Monthly</option>
          <option value="yearly">Yearly</option>
        </select>
      </div>

      <div className="col-span-6 sm:col-span-2 flex items-center gap-2">
        <Switch
          checked={rollover}
          onCheckedChange={setRollover}
          disabled={period !== "monthly"}
          data-testid={`budget-rollover-${category.id}`}
        />
        <span className="text-xs text-[#656C5A]">
          {period === "monthly" ? "Rollover" : "n/a"}
        </span>
      </div>

      <div className="col-span-6 sm:col-span-2">
        {progress ? (
          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className={styles.text}>{verb} {formatGBP(progress.spent)}</span>
              <span className="text-[#656C5A]">{progress.percent.toFixed(0)}%</span>
            </div>
            <div className="h-2 bg-[#EAE3D9] rounded-full overflow-hidden relative">
              <div
                className={`h-full ${styles.bar} transition-all duration-500`}
                style={{ width: `${percent}%` }}
              />
              {overflow > 0 && (
                <div
                  className="absolute inset-y-0 right-0 bg-[#D96C4E]/40 animate-pulse"
                  style={{ width: `${Math.min(20, overflow / 5)}%` }}
                />
              )}
            </div>
            <div className="text-xs text-[#656C5A]">
              of {formatGBP(progress.effective_amount)}
              {progress.effective_amount !== progress.amount && (
                <span className="ml-1 text-[#728A66]">(rolled)</span>
              )}
            </div>
          </div>
        ) : (
          <div className="text-xs text-[#656C5A]">Save to start tracking</div>
        )}
      </div>

      <div className="col-span-12 sm:col-span-1 flex justify-end">
        <Button
          size="sm"
          onClick={persist}
          disabled={saving}
          data-testid={`budget-save-${category.id}`}
          className="bg-[#364C2E] hover:bg-[#22331D] text-white h-9 px-3"
        >
          <Save className="w-3.5 h-3.5" />
        </Button>
      </div>
    </motion.div>
  );
}

export default function Budgets() {
  const { active } = useProject();
  const [categories, setCategories] = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [progress, setProgress] = useState({ items: [] });
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(false);

  const reload = async () => {
    if (!active) return;
    setLoading(true);
    try {
      const [c, b, p] = await Promise.all([
        api.get("/categories", { params: { project_id: active.id } }),
        api.get("/budgets", { params: { project_id: active.id } }),
        api.get("/budgets/progress", { params: { project_id: active.id, year, month } }),
      ]);
      setCategories(c.data);
      setBudgets(b.data);
      setProgress(p.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, year, month]);

  const budgetByCategory = useMemo(() => {
    const map = {};
    for (const b of budgets) map[b.category_id] = b;
    return map;
  }, [budgets]);

  const progressByCategory = useMemo(() => {
    const map = {};
    for (const p of progress.items || []) map[p.category_id] = p;
    return map;
  }, [progress]);

  const overItems = (progress.items || []).filter((p) => p.status === "over");

  if (!active) {
    return (
      <div className="py-16 text-center text-[#656C5A]" data-testid="budgets-no-project">
        Select or create a project to manage budgets.
      </div>
    );
  }

  const expenseCats = categories.filter((c) => c.type === "expense");
  const incomeCats = categories.filter((c) => c.type === "income");

  return (
    <div className="space-y-8" data-testid="budgets-page">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Budgets</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Set targets per category
          </h1>
          <p className="text-[#656C5A] mt-1 text-sm">
            Monthly spending caps for expenses, monthly or yearly targets for income. Rollover carries unused monthly budget forward.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Period</span>
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            data-testid="budgets-month-select"
            className="bg-white border border-[#EAE3D9] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#364C2E]/20"
          >
            {MONTHS.map((m, i) => (
              <option key={m} value={i + 1}>{m}</option>
            ))}
          </select>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            data-testid="budgets-year-select"
            className="bg-white border border-[#EAE3D9] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#364C2E]/20"
          >
            {[year - 1, year, year + 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {overItems.length > 0 && (
        <Card className="p-4 bg-[#D96C4E]/8 border-[#D96C4E]/30 shadow-none" data-testid="budgets-over-banner">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-[#D96C4E] shrink-0 mt-0.5" />
            <div className="text-sm">
              <span className="font-medium text-[#D96C4E]">
                {overItems.length} {overItems.length === 1 ? "category is" : "categories are"} over budget
              </span>
              <div className="text-[#656C5A] mt-1">
                {overItems.slice(0, 4).map((p) => p.category_name).join(", ")}
                {overItems.length > 4 ? ` and ${overItems.length - 4} more` : ""}
              </div>
            </div>
          </div>
        </Card>
      )}

      <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
        <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Expense budgets</h3>
        <p className="text-xs text-[#656C5A] mt-0.5 mb-4">A spending cap per category. Set 0 to remove.</p>

        <div className="hidden sm:grid grid-cols-12 gap-4 text-xs text-[#656C5A] uppercase tracking-wide pb-2 border-b border-[#EAE3D9]">
          <div className="col-span-3">Category</div>
          <div className="col-span-2">Amount</div>
          <div className="col-span-2">Period</div>
          <div className="col-span-2">Rollover</div>
          <div className="col-span-2">Progress</div>
          <div className="col-span-1 text-right">Save</div>
        </div>

        {loading && expenseCats.length === 0 ? (
          <div className="py-12 text-center text-sm text-[#656C5A]">Loading...</div>
        ) : expenseCats.length === 0 ? (
          <div className="py-12 text-center text-sm text-[#656C5A]">
            No expense categories yet. Create one on the Categories page.
          </div>
        ) : (
          expenseCats.map((c) => (
            <BudgetRow
              key={c.id}
              category={c}
              budget={budgetByCategory[c.id]}
              progress={progressByCategory[c.id]}
              onChange={reload}
            />
          ))
        )}
      </Card>

      <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
        <div className="flex items-center gap-2 mb-1">
          <Wallet className="w-4 h-4 text-[#4B6B40]" />
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Income targets</h3>
        </div>
        <p className="text-xs text-[#656C5A] mb-4">How much you expect to receive per period.</p>

        {incomeCats.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#656C5A]">No income categories.</div>
        ) : (
          incomeCats.map((c) => (
            <BudgetRow
              key={c.id}
              category={c}
              budget={budgetByCategory[c.id]}
              progress={progressByCategory[c.id]}
              onChange={reload}
            />
          ))
        )}
      </Card>
    </div>
  );
}
