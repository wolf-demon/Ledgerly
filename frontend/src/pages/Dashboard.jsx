import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useProject } from "../lib/projectContext";
import api, { formatGBP, MONTHS } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ArrowUpRight, ArrowDownRight, Wallet, TrendingUp, Upload, Tags, AlertCircle } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import BudgetSummary from "../components/BudgetSummary";

export default function Dashboard({ onNewProject }) {
  const { active, projects, loading: projLoading } = useProject();
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [recent, setRecent] = useState([]);
  const [uncategorizedCount, setUncategorizedCount] = useState(0);
  const [years, setYears] = useState([new Date().getFullYear()]);

  useEffect(() => {
    if (!active) return;
    (async () => {
      const yrs = await api.get("/analytics/years", { params: { project_id: active.id } });
      const list = yrs.data.years.length ? yrs.data.years : [new Date().getFullYear()];
      setYears(list);
      if (!list.includes(year)) setYear(list[0]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    if (!active) return;
    (async () => {
      const [a, t, u] = await Promise.all([
        api.get("/analytics/yearly", { params: { project_id: active.id, year } }),
        api.get("/transactions", { params: { project_id: active.id, limit: 8 } }),
        api.get("/transactions", { params: { project_id: active.id, uncategorized: true, limit: 1 } }),
      ]);
      setData(a.data);
      setRecent(t.data);
      // count uncategorized properly
      const all = await api.get("/transactions", { params: { project_id: active.id, uncategorized: true, limit: 5000 } });
      setUncategorizedCount(all.data.length);
    })();
  }, [active, year]);

  if (projLoading) {
    return <div className="p-8 text-[#656C5A]">Loading...</div>;
  }

  if (!active) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center" data-testid="empty-no-project">
        <div className="w-16 h-16 rounded-md bg-[#F4EBE1] mx-auto flex items-center justify-center">
          <Wallet className="w-8 h-8 text-[#364C2E]" />
        </div>
        <h1 className="mt-6 text-3xl sm:text-4xl font-semibold tracking-tight" style={{ fontFamily: "Work Sans" }}>
          Welcome to Ledgerly
        </h1>
        <p className="mt-3 text-[#656C5A] leading-relaxed">
          Create your first project to start uploading bank statements and tracking your monthly income & expenditure.
        </p>
        <Button
          onClick={onNewProject}
          data-testid="empty-create-project-btn"
          className="mt-8 bg-[#364C2E] hover:bg-[#22331D] text-white px-6 py-2"
        >
          Create your first project
        </Button>
        {projects.length === 0 && (
          <p className="text-xs text-[#656C5A] mt-4">e.g. "Personal", "Business", "Joint household"</p>
        )}
      </div>
    );
  }

  const totalIncome = data?.total_income || 0;
  const totalExpense = data?.total_expense || 0;
  const net = data?.net || 0;
  const savingsRate = totalIncome > 0 ? (net / totalIncome) * 100 : 0;

  const monthlyData = (data?.monthly_income || []).map((inc, i) => ({
    month: MONTHS[i],
    Income: inc,
    Expense: data?.monthly_expense?.[i] || 0,
  }));

  const expenseCategories = (data?.categories || [])
    .filter((c) => c.type === "expense" && c.total < 0)
    .map((c) => ({ name: c.name, value: Math.abs(c.total), color: c.color }))
    .sort((a, b) => b.value - a.value);

  const COLORS = ["#364C2E", "#D96C4E", "#D1A77E", "#728A66", "#E3C8AA", "#4B6B40"];

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Overview</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            {active.name}
          </h1>
          {active.description && <p className="text-[#656C5A] mt-1">{active.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Year</span>
          <select
            value={year}
            data-testid="dashboard-year-select"
            onChange={(e) => setYear(Number(e.target.value))}
            className="bg-white border border-[#EAE3D9] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#364C2E]/20"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {uncategorizedCount > 0 && (
        <Link to="/transactions?filter=uncategorized" className="block">
          <div className="flex items-center gap-3 px-4 py-3 rounded-md bg-[#D96C4E]/8 border border-[#D96C4E]/30 hover:bg-[#D96C4E]/12 transition-colors" data-testid="uncategorized-banner">
            <AlertCircle className="w-5 h-5 text-[#D96C4E]" />
            <div className="text-sm">
              <span className="font-medium">{uncategorizedCount}</span> uncategorized transactions need your attention.
              <span className="text-[#D96C4E] ml-2 underline">Categorize now →</span>
            </div>
          </div>
        </Link>
      )}

      {/* Summary cards */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.07 } } }}
      >
        {[
          {
            label: "Total Income",
            value: formatGBP(totalIncome),
            icon: ArrowUpRight,
            tone: "income",
            sub: `${year}`,
          },
          {
            label: "Total Expense",
            value: formatGBP(totalExpense),
            icon: ArrowDownRight,
            tone: "expense",
            sub: `${year}`,
          },
          {
            label: "Net",
            value: formatGBP(net),
            icon: Wallet,
            tone: net >= 0 ? "income" : "expense",
            sub: "Income minus expense",
          },
          {
            label: "Savings rate",
            value: `${savingsRate.toFixed(1)}%`,
            icon: TrendingUp,
            tone: savingsRate >= 0 ? "income" : "expense",
            sub: "Net / income",
          },
        ].map((s) => (
          <motion.div
            key={s.label}
            variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}
          >
            <Card className="p-6 bg-white border-[#EAE3D9] shadow-none hover:-translate-y-0.5 hover:shadow-md hover:border-[#D1A77E] transition-all duration-300">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-[#656C5A]">{s.label}</p>
                  <p className="text-2xl font-semibold mt-2" style={{ fontFamily: "Work Sans" }}>{s.value}</p>
                  <p className="text-xs text-[#656C5A] mt-1">{s.sub}</p>
                </div>
                <div className={`w-9 h-9 rounded-md flex items-center justify-center ${
                  s.tone === "income" ? "bg-[#4B6B40]/10 text-[#4B6B40]" : "bg-[#D96C4E]/10 text-[#D96C4E]"
                }`}>
                  <s.icon className="w-5 h-5" />
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 p-6 bg-white border-[#EAE3D9] shadow-none">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Monthly cashflow</h3>
              <p className="text-xs text-[#656C5A] mt-0.5">Income vs expense, {year}</p>
            </div>
          </div>
          <div className="h-72" data-testid="monthly-cashflow-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE3D9" vertical={false} />
                <XAxis dataKey="month" stroke="#656C5A" fontSize={12} />
                <YAxis stroke="#656C5A" fontSize={12} />
                <Tooltip
                  formatter={(v) => formatGBP(v)}
                  contentStyle={{ background: "#FFFFFF", border: "1px solid #EAE3D9", borderRadius: 6 }}
                />
                <Legend />
                <Bar dataKey="Income" fill="#4B6B40" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Expense" fill="#D96C4E" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Expense breakdown</h3>
          <p className="text-xs text-[#656C5A] mt-0.5 mb-4">Top expense categories</p>
          {expenseCategories.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-sm text-[#656C5A]">
              No expense data yet.
            </div>
          ) : (
            <div className="h-64" data-testid="expense-pie-chart">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={expenseCategories}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={85}
                    paddingAngle={2}
                  >
                    {expenseCategories.map((entry, i) => (
                      <Cell key={i} fill={entry.color || COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => formatGBP(v)} contentStyle={{ background: "#FFFFFF", border: "1px solid #EAE3D9", borderRadius: 6 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="mt-3 space-y-1.5 max-h-32 overflow-auto scrollbar-thin">
            {expenseCategories.slice(0, 6).map((c, i) => (
              <div key={c.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: c.color || COLORS[i % COLORS.length] }} />
                  <span className="truncate text-[#1F2E1B]">{c.name}</span>
                </div>
                <span className="text-[#656C5A]">{formatGBP(c.value)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Budget summary */}
      <BudgetSummary projectId={active.id} year={year} month={new Date().getMonth() + 1} />

      {/* Recent transactions */}
      <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Recent transactions</h3>
            <p className="text-xs text-[#656C5A] mt-0.5">Last imported items</p>
          </div>
          <div className="flex gap-2">
            <Link to="/upload">
              <Button variant="outline" className="border-[#EAE3D9] hover:bg-[#F4EBE1]" data-testid="dash-upload-btn">
                <Upload className="w-4 h-4 mr-2" /> Upload
              </Button>
            </Link>
            <Link to="/categories">
              <Button variant="outline" className="border-[#EAE3D9] hover:bg-[#F4EBE1]" data-testid="dash-categories-btn">
                <Tags className="w-4 h-4 mr-2" /> Categories
              </Button>
            </Link>
          </div>
        </div>
        {recent.length === 0 ? (
          <div className="py-12 text-center text-[#656C5A]">
            No transactions yet. Upload a bank statement to begin.
          </div>
        ) : (
          <div className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#656C5A] border-b border-[#EAE3D9]">
                  <th className="py-3 font-medium">Date</th>
                  <th className="py-3 font-medium">Description</th>
                  <th className="py-3 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id} className="border-b border-[#EAE3D9]/50">
                    <td className="py-3 text-[#656C5A]">{t.date}</td>
                    <td className="py-3 truncate max-w-md">{t.description}</td>
                    <td className={`py-3 text-right font-medium ${t.amount >= 0 ? "text-[#4B6B40]" : "text-[#D96C4E]"}`}>
                      {formatGBP(t.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
