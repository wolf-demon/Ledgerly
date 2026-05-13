import React, { useEffect, useState, useCallback } from "react";
import { useProject } from "../lib/projectContext";
import api, { formatGBP } from "../lib/api";
import { Card } from "../components/ui/card";
import { motion } from "framer-motion";
import { Repeat, TrendingDown, TrendingUp, Calendar, Sparkles } from "lucide-react";
import { useFetchGuard } from "../lib/useFetchGuard";

export default function Recurring() {
  const { active, revision } = useProject();
  const guard = useFetchGuard();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lookback, setLookback] = useState(6);

  const load = useCallback(async () => {
    if (!active) { setData(null); return; }
    setLoading(true);
    guard(async ({ isStale }) => {
      try {
        const res = await api.get("/analytics/recurring", {
          params: { project_id: active.id, lookback_months: lookback },
        });
        if (isStale()) return;
        setData(res.data);
      } finally {
        if (!isStale()) setLoading(false);
      }
    });
  }, [active, lookback, guard]);

  useEffect(() => {
    load();
  }, [load, revision]);

  if (!active) return <div className="text-[var(--c-muted)]">Create or select a project first.</div>;

  const expense = (data?.recurring || []).filter((r) => r.type === "expense");
  const income = (data?.recurring || []).filter((r) => r.type === "income");
  const fc = data?.forecast || { monthly_total_expense: 0, monthly_total_income: 0, monthly_net: 0 };

  const Row = ({ r }) => (
    <div
      data-testid={`recurring-row-${r.merchant_key}`}
      className="grid grid-cols-12 gap-3 items-center px-4 py-3 rounded-md border border-[color-mix(in_srgb,var(--c-border)_70%,transparent)] hover:border-[var(--c-accent)] hover:bg-[color-mix(in_srgb,var(--c-surface)_30%,transparent)] transition-all"
    >
      <div className="col-span-5 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: r.category_color }} />
          <span className="font-medium truncate" title={r.sample_description}>{r.sample_description}</span>
        </div>
        <div className="text-xs text-[var(--c-muted)] mt-0.5 flex items-center gap-2">
          <span>{r.category_name}</span>
          <span className="text-[var(--c-accent)]">•</span>
          <span className="capitalize">{r.cadence}</span>
          <span className="text-[var(--c-accent)]">•</span>
          <span>{r.occurrences} hits</span>
        </div>
      </div>
      <div className="col-span-3 text-xs text-[var(--c-muted)]">
        <div className="flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5" />
          Next: <span className="text-[var(--c-ink)] font-medium">{r.next_expected}</span>
        </div>
        <div className="mt-0.5">Last: {r.last_seen}</div>
      </div>
      <div className="col-span-2 text-right text-sm">
        <div className="text-[var(--c-muted)] text-xs">Avg</div>
        <div className={`font-medium ${r.avg_amount >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`}>
          {formatGBP(r.avg_amount)}
        </div>
      </div>
      <div className="col-span-2 text-right text-sm">
        <div className="text-[var(--c-muted)] text-xs">Per month</div>
        <div className={`font-semibold ${r.monthly_estimate >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`} style={{ fontFamily: "Work Sans" }}>
          {formatGBP(r.monthly_estimate)}
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Insights</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Recurring & forecast
          </h1>
          <p className="text-[var(--c-muted)] mt-1 text-sm flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5" /> Detected merchants that repeat monthly/weekly. Used to forecast your typical month.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Lookback</span>
          <select
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
            data-testid="recurring-lookback-select"
            className="bg-[var(--c-card)] border border-[var(--c-border)] rounded-md px-3 py-1.5 text-sm focus:outline-none"
          >
            <option value={3}>3 months</option>
            <option value={6}>6 months</option>
            <option value={12}>12 months</option>
          </select>
        </div>
      </div>

      <motion.div
        className="grid grid-cols-1 md:grid-cols-3 gap-4"
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
      >
        {[
          { label: "Forecast monthly income", value: fc.monthly_total_income, tone: "income", icon: TrendingUp },
          { label: "Forecast monthly expense", value: fc.monthly_total_expense, tone: "expense", icon: TrendingDown },
          { label: "Forecast monthly net", value: fc.monthly_net, tone: fc.monthly_net >= 0 ? "income" : "expense", icon: Repeat },
        ].map((s) => (
          <motion.div key={s.label} variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}>
            <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">{s.label}</p>
                  <p
                    className={`text-2xl font-semibold mt-2 ${s.tone === "income" ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`}
                    style={{ fontFamily: "Work Sans" }}
                  >
                    {formatGBP(s.value)}
                  </p>
                  <p className="text-xs text-[var(--c-muted)] mt-1">Based on last {lookback} months</p>
                </div>
                <div className={`w-9 h-9 rounded-md flex items-center justify-center ${
                  s.tone === "income" ? "bg-[color-mix(in_srgb,var(--c-success)_10%,transparent)] text-[var(--c-success)]" : "bg-[color-mix(in_srgb,var(--c-danger)_10%,transparent)] text-[var(--c-danger)]"
                }`}>
                  <s.icon className="w-5 h-5" />
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {loading && <div className="text-[var(--c-muted)]">Analyzing patterns...</div>}

      {!loading && (
        <>
          <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Recurring expenses</h3>
              <span className="text-xs text-[var(--c-muted)]">{expense.length} merchants</span>
            </div>
            {expense.length === 0 ? (
              <p className="text-sm text-[var(--c-muted)]" data-testid="empty-recurring-expense">
                No recurring expenses detected yet. Upload at least 2 months of statements.
              </p>
            ) : (
              <div className="space-y-2" data-testid="recurring-expense-list">
                {expense.map((r) => <Row key={r.merchant_key} r={r} />)}
              </div>
            )}
          </Card>

          <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Recurring income</h3>
              <span className="text-xs text-[var(--c-muted)]">{income.length} merchants</span>
            </div>
            {income.length === 0 ? (
              <p className="text-sm text-[var(--c-muted)]" data-testid="empty-recurring-income">
                No recurring income detected yet.
              </p>
            ) : (
              <div className="space-y-2" data-testid="recurring-income-list">
                {income.map((r) => <Row key={r.merchant_key} r={r} />)}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
