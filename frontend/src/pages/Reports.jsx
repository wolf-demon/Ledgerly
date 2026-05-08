import React, { useEffect, useState, useCallback } from "react";
import { useProject } from "../lib/projectContext";
import api, { formatGBP, MONTHS } from "../lib/api";
import { Card } from "../components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";

export default function Reports() {
  const { active } = useProject();
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
    const res = await api.get("/analytics/yearly", { params: { project_id: active.id, year: useYear } });
    setData(res.data);
  }, [active, year]);

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

  if (!active) return <div className="text-[#656C5A]">Create or select a project first.</div>;
  if (!data) return <div className="text-[#656C5A]">Loading report...</div>;

  // Heatmap intensity helper
  const allValues = data.categories.flatMap((c) => c.monthly.map((v) => Math.abs(v)));
  const maxVal = Math.max(...allValues, 1);

  const cellShade = (val, color) => {
    const ratio = Math.abs(val) / maxVal;
    const opacity = ratio === 0 ? 0 : Math.max(0.18, ratio);
    return { backgroundColor: color, opacity };
  };

  const expense = data.categories.filter((c) => c.type === "expense");
  const income = data.categories.filter((c) => c.type === "income");

  const renderTable = (rows, type) => (
    <div className="overflow-x-auto" data-testid={`heatmap-${type}`}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#EAE3D9]">
            <th className="text-left py-3 px-3 font-medium text-[#656C5A] sticky left-0 bg-white min-w-[180px]">Category</th>
            {MONTHS.map((m) => (
              <th key={m} className="text-center py-3 px-2 font-medium text-[#656C5A] text-xs">{m}</th>
            ))}
            <th className="text-right py-3 px-3 font-medium text-[#656C5A] min-w-[110px]">Year total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr
              key={c.category_id || "uncat"}
              className={`border-b border-[#EAE3D9]/50 cursor-pointer ${selectedCategory === c.category_id ? "bg-[#F4EBE1]/50" : "hover:bg-[#F4EBE1]/30"}`}
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
                    className="rounded px-1 py-1 text-xs heatmap-cell"
                    style={{
                      ...cellShade(v, c.color),
                      color: Math.abs(v) / maxVal > 0.4 ? "#FFFFFF" : "#1F2E1B",
                    }}
                    title={`${MONTHS[i]} ${year}: ${formatGBP(v)}`}
                  >
                    {v === 0 ? "—" : formatGBP(Math.abs(v)).replace(".00", "")}
                  </div>
                </td>
              ))}
              <td className="py-3 px-3 text-right font-semibold">
                {formatGBP(Math.abs(c.total))}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={14} className="py-8 text-center text-[#656C5A]">No {type} data for {year}.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Analysis</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            Yearly report
          </h1>
          <p className="text-[#656C5A] mt-1 text-sm">Heatmap of category spend & income by month. Click any category for transaction-level detail.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Year</span>
          <select
            value={year}
            data-testid="report-year-select"
            onChange={(e) => { setYear(Number(e.target.value)); setSelectedCategory(null); setCategoryDetail(null); }}
            className="bg-white border border-[#EAE3D9] rounded-md px-3 py-1.5 text-sm focus:outline-none"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5 bg-white border-[#EAE3D9] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[#656C5A]">Total income</p>
          <p className="text-2xl font-semibold mt-2 text-[#4B6B40]" style={{ fontFamily: "Work Sans" }}>{formatGBP(data.total_income)}</p>
        </Card>
        <Card className="p-5 bg-white border-[#EAE3D9] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[#656C5A]">Total expense</p>
          <p className="text-2xl font-semibold mt-2 text-[#D96C4E]" style={{ fontFamily: "Work Sans" }}>{formatGBP(data.total_expense)}</p>
        </Card>
        <Card className="p-5 bg-white border-[#EAE3D9] shadow-none">
          <p className="text-xs uppercase tracking-[0.18em] text-[#656C5A]">Net</p>
          <p className={`text-2xl font-semibold mt-2 ${data.net >= 0 ? "text-[#4B6B40]" : "text-[#D96C4E]"}`} style={{ fontFamily: "Work Sans" }}>{formatGBP(data.net)}</p>
        </Card>
      </div>

      <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
        <Tabs defaultValue="expense">
          <TabsList className="bg-[#F4EBE1]">
            <TabsTrigger value="expense" data-testid="tab-expense">Expense</TabsTrigger>
            <TabsTrigger value="income" data-testid="tab-income">Income</TabsTrigger>
          </TabsList>
          <TabsContent value="expense" className="mt-5">{renderTable(expense, "expense")}</TabsContent>
          <TabsContent value="income" className="mt-5">{renderTable(income, "income")}</TabsContent>
        </Tabs>
      </Card>

      {selectedCategory && categoryDetail && (
        <Card className="p-6 bg-white border-[#EAE3D9] shadow-none" data-testid="category-detail-panel">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-[#656C5A]">Category breakdown</p>
              <h3 className="text-xl font-medium mt-1" style={{ fontFamily: "Work Sans" }}>
                {data.categories.find((c) => c.category_id === selectedCategory)?.name}
              </h3>
            </div>
            <button
              onClick={() => { setSelectedCategory(null); setCategoryDetail(null); }}
              className="text-sm text-[#656C5A] hover:text-[#1F2E1B]"
              data-testid="close-detail-btn"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-12 gap-2 mb-6">
            {categoryDetail.monthly.map((v, i) => (
              <div key={i} className="text-center">
                <div className="text-xs text-[#656C5A] mb-1">{MONTHS[i]}</div>
                <div className="rounded-md py-2 px-1 text-xs font-medium" style={{
                  backgroundColor: v < 0 ? "#D96C4E1A" : v > 0 ? "#4B6B401A" : "#F4EBE1",
                  color: v < 0 ? "#D96C4E" : v > 0 ? "#4B6B40" : "#656C5A",
                }}>
                  {v === 0 ? "—" : formatGBP(Math.abs(v))}
                </div>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#656C5A] border-b border-[#EAE3D9]">
                  <th className="py-2 px-3 font-medium">Date</th>
                  <th className="py-2 px-3 font-medium">Description</th>
                  <th className="py-2 px-3 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {categoryDetail.transactions.map((t) => (
                  <tr key={t.id} className="border-b border-[#EAE3D9]/50">
                    <td className="py-2 px-3 text-[#656C5A] whitespace-nowrap">{t.date}</td>
                    <td className="py-2 px-3 truncate max-w-md">{t.description}</td>
                    <td className={`py-2 px-3 text-right font-medium ${t.amount >= 0 ? "text-[#4B6B40]" : "text-[#D96C4E]"}`}>
                      {formatGBP(t.amount)}
                    </td>
                  </tr>
                ))}
                {categoryDetail.transactions.length === 0 && (
                  <tr><td colSpan={3} className="py-6 text-center text-[#656C5A]">No transactions.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
