import React, { useEffect, useState, useCallback } from "react";
import { useProject } from "../lib/projectContext";
import { useBankAccount } from "../lib/bankAccountContext";
import api, { formatGBP, MONTHS } from "../lib/api";
import { Card } from "../components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";

export default function Reports() {
  const { active } = useProject();
  const { selectedId: bankAccountId } = useBankAccount();
  const [years, setYears] = useState([new Date().getFullYear()]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [categoryDetail, setCategoryDetail] = useState(null);

  const load = useCallback(async () => {
    if (!active) return;
    const yrs = await api.get("/analytics/years", { params: { project_id: active.id } });
    setYears(yrs.data.years);
    const useYear = yrs.data.years.includes(year) ? year : yrs.data.years[0];
    if (useYear !== year) setYear(useYear);
    const params = { project_id: active.id, year: useYear };
    if (bankAccountId) params.bank_account_id = bankAccountId;
    const res = await api.get("/analytics/yearly", { params });
    setData(res.data);
  }, [active, year, bankAccountId]);

  useEffect(() => {
    load();
  }, [load]);

  const loadDetail = useCallback(async (catId) => {
    if (!active || !catId) return;
    const res = await api.get(`/analytics/category/${catId}`, { params: { project_id: active.id, year } });
    setCategoryDetail(res.data);
  }, [active, year]);

  useEffect(() => {
    if (selectedCategory) loadDetail(selectedCategory);
  }, [selectedCategory, loadDetail]);

  if (!active) return <div className="text-[var(--c-muted)]">Create or select a project first.</div>;
  if (!data) return <div className="text-[var(--c-muted)]">Loading report...</div>;

  // Heatmap intensity helper
  const allValues = data.categories.flatMap((c) => c.monthly.map((v) => Math.abs(v)));
  const maxVal = Math.max(...allValues, 1);

  const cellShade = (val, color) => {
    const ratio = Math.abs(val) / maxVal;
    // Keep cells light so dark text stays high-contrast. Most active month ~30%.
    const opacity = ratio === 0 ? 0 : Math.min(0.30, 0.05 + ratio * 0.30);
    return { backgroundColor: color, opacity };
  };

  const expense = data.categories.filter((c) => c.type === "expense");
  const income = data.categories.filter((c) => c.type === "income");

  const renderTable = (rows, type) => (
    <div className="overflow-x-auto" data-testid={`heatmap-${type}`}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[var(--c-border)]">
            <th className="text-left py-3 px-3 font-medium text-[var(--c-muted)] sticky left-0 bg-[var(--c-card)] min-w-[180px]">Category</th>
            {MONTHS.map((m) => (
              <th key={m} className="text-center py-3 px-2 font-medium text-[var(--c-muted)] text-xs">{m}</th>
            ))}
            <th className="text-right py-3 px-3 font-medium text-[var(--c-muted)] min-w-[110px]">Year total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr
              key={c.category_id || "uncat"}
              className={`border-b border-[color-mix(in_srgb,var(--c-border)_50%,transparent)] cursor-pointer ${selectedCategory === c.category_id ? "bg-[color-mix(in_srgb,var(--c-surface)_50%,transparent)]" : "hover:bg-[color-mix(in_srgb,var(--c-surface)_30%,transparent)]"}`}
              onClick={() => c.category_id && setSelectedCategory(c.category_id)}
              data-testid={`heatmap-row-${c.category_id || "uncat"}`}
            >
              <td className="py-3 px-3 font-medium sticky left-0 bg-inherit">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: c.color }} />
                  <span className="truncate">{c.name}</span>
                </div>
              </td>
              {c.monthly.map((v, i) => (
                <td key={i} className="text-center px-1 py-2">
                  <div
                    className="relative rounded heatmap-cell"
                    style={{
                      ...cellShade(v, c.color),
                    }}
                    title={`${MONTHS[i]} ${year}: ${formatGBP(v)}`}
                  >
                    {/* Number lives in a sibling so the parent's opacity tint
                        doesn't drag the text alpha down too. */}
                  </div>
                  <div
                    className="-mt-[26px] mx-0.5 px-1 py-1 text-xs font-semibold relative"
                    style={{ color: "var(--c-ink)" }}
                  >
                    {v === 0 ? <span className="text-[var(--c-muted-2)]">—</span> : formatGBP(Math.abs(v)).replace(".00", "")}
                  </div>
                </td>
              ))}
              <td className="py-3 px-3 text-right font-semibold">
                {formatGBP(Math.abs(c.total))}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={14} className="py-8 text-center text-[var(--c-muted)]">No {type} data for {year}.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Analysis</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Yearly report
          </h1>
          <p className="text-[var(--c-muted)] mt-1 text-sm">Heatmap of category spend & income by month. Click any category for transaction-level detail.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Year</span>
          <select
            value={year}
            data-testid="report-year-select"
            onChange={(e) => { setYear(Number(e.target.value)); setSelectedCategory(null); setCategoryDetail(null); }}
            className="bg-[var(--c-card)] border border-[var(--c-border)] rounded-md px-3 py-1.5 text-sm focus:outline-none"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">Total income</p>
          <p className="text-2xl font-semibold mt-2 text-[var(--c-success)]" style={{ fontFamily: "Work Sans" }}>{formatGBP(data.total_income)}</p>
        </Card>
        <Card className="p-5 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">Total expense</p>
          <p className="text-2xl font-semibold mt-2 text-[var(--c-danger)]" style={{ fontFamily: "Work Sans" }}>{formatGBP(data.total_expense)}</p>
        </Card>
        <Card className="p-5 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">Net</p>
          <p className={`text-2xl font-semibold mt-2 ${data.net >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`} style={{ fontFamily: "Work Sans" }}>{formatGBP(data.net)}</p>
        </Card>
      </div>

      <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
        <Tabs defaultValue="expense">
          <TabsList className="bg-[var(--c-surface)]">
            <TabsTrigger value="expense" data-testid="tab-expense">Expense</TabsTrigger>
            <TabsTrigger value="income" data-testid="tab-income">Income</TabsTrigger>
          </TabsList>
          <TabsContent value="expense" className="mt-5">{renderTable(expense, "expense")}</TabsContent>
          <TabsContent value="income" className="mt-5">{renderTable(income, "income")}</TabsContent>
        </Tabs>
      </Card>

      {selectedCategory && categoryDetail && (
        <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none" data-testid="category-detail-panel">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">Category breakdown</p>
              <h3 className="text-xl font-medium mt-1" style={{ fontFamily: "Work Sans" }}>
                {data.categories.find((c) => c.category_id === selectedCategory)?.name}
              </h3>
            </div>
            <button
              onClick={() => { setSelectedCategory(null); setCategoryDetail(null); }}
              className="text-sm text-[var(--c-muted)] hover:text-[var(--c-ink)]"
              data-testid="close-detail-btn"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-12 gap-2 mb-6">
            {categoryDetail.monthly.map((v, i) => (
              <div key={i} className="text-center">
                <div className="text-xs text-[var(--c-muted)] mb-1">{MONTHS[i]}</div>
                <div className="rounded-md py-2 px-1 text-xs font-medium" style={{
                  backgroundColor: v < 0 ? "color-mix(in srgb, var(--c-danger) 10%, transparent)" : v > 0 ? "color-mix(in srgb, var(--c-success) 10%, transparent)" : "var(--c-surface)",
                  color: v < 0 ? "var(--c-danger)" : v > 0 ? "var(--c-success)" : "var(--c-muted)",
                }}>
                  {v === 0 ? "—" : formatGBP(Math.abs(v))}
                </div>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--c-muted)] border-b border-[var(--c-border)]">
                  <th className="py-2 px-3 font-medium">Date</th>
                  <th className="py-2 px-3 font-medium">Description</th>
                  <th className="py-2 px-3 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {categoryDetail.transactions.map((t) => (
                  <tr key={t.id} className="border-b border-[color-mix(in_srgb,var(--c-border)_50%,transparent)]">
                    <td className="py-2 px-3 text-[var(--c-muted)] whitespace-nowrap">{t.date}</td>
                    <td className="py-2 px-3 truncate max-w-md">{t.description}</td>
                    <td className={`py-2 px-3 text-right font-medium ${t.amount >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`}>
                      {formatGBP(t.amount)}
                    </td>
                  </tr>
                ))}
                {categoryDetail.transactions.length === 0 && (
                  <tr><td colSpan={3} className="py-6 text-center text-[var(--c-muted)]">No transactions.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
