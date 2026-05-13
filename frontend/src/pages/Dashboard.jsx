import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useProject } from "../lib/projectContext";
import { useBankAccount } from "../lib/bankAccountContext";
import api, { formatGBP, MONTHS } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { ArrowUpRight, ArrowDownRight, Wallet, TrendingUp, Upload, Tags, AlertCircle } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import BudgetSummary from "../components/BudgetSummary";
import { useThemeColors } from "../lib/useThemeColors";
import { useFetchGuard } from "../lib/useFetchGuard";

export default function Dashboard({ onNewProject }) {
  const { active, projects, loading: projLoading, revision } = useProject();
  const { selectedId: bankAccountId } = useBankAccount();
  const tc = useThemeColors();
  const guard = useFetchGuard();
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [recent, setRecent] = useState([]);
  const [uncategorizedCount, setUncategorizedCount] = useState(0);
  const [years, setYears] = useState([new Date().getFullYear()]);

  useEffect(() => {
    if (!active) {
      // Clear immediately on project switch / delete so the previous project's
      // numbers don't linger.
      setData(null);
      setRecent([]);
      setUncategorizedCount(0);
      return;
    }
    guard(async ({ isStale }) => {
      const yrs = await api.get("/analytics/years", { params: { project_id: active.id } });
      if (isStale()) return;
      const list = yrs.data.years.length ? yrs.data.years : [new Date().getFullYear()];
      setYears(list);
      if (!list.includes(year)) setYear(list[0]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, revision]);

  useEffect(() => {
    if (!active) return;
    guard(async ({ isStale }) => {
      const extra = bankAccountId ? { bank_account_id: bankAccountId } : {};
      const [a, t] = await Promise.all([
        api.get("/analytics/yearly", { params: { project_id: active.id, year, ...extra } }),
        api.get("/transactions", { params: { project_id: active.id, limit: 8, ...extra } }),
      ]);
      if (isStale()) return;
      setData(a.data);
      setRecent(t.data);
      const all = await api.get("/transactions", { params: { project_id: active.id, uncategorized: true, limit: 5000, ...extra } });
      if (isStale()) return;
      setUncategorizedCount(all.data.length);
    });
  }, [active, year, bankAccountId, revision, guard]);

  if (projLoading) {
    return <div className="p-8 text-[var(--c-muted)]">Loading...</div>;
  }

  if (!active) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center" data-testid="empty-no-project">
        <div className="w-16 h-16 rounded-md bg-[var(--c-surface)] mx-auto flex items-center justify-center">
          <Wallet className="w-8 h-8 text-[var(--c-primary)]" />
        </div>
        <h1 className="mt-6 text-3xl sm:text-4xl font-semibold tracking-tight" style={{ fontFamily: "Work Sans" }}>
          Welcome to Ledgerly
        </h1>
        <p className="mt-3 text-[var(--c-muted)] leading-relaxed">
          Create your first project to start uploading bank statements and tracking your monthly income & expenditure.
        </p>
        <Button
          onClick={onNewProject}
          data-testid="empty-create-project-btn"
          className="mt-8 bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)] px-6 py-2"
        >
          Create your first project
        </Button>
        {projects.length === 0 && (
          <p className="text-xs text-[var(--c-muted)] mt-4">e.g. "Personal", "Business", "Joint household"</p>
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

  const COLORS = [tc["c-primary"], tc["c-danger"], tc["c-accent"], tc["c-primary-soft"], tc["c-accent-2"], tc["c-success"]].filter(Boolean);

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Overview</p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
            {active.name}
          </h1>
          {active.description && <p className="text-[var(--c-muted)] mt-1">{active.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Year</span>
          <select
            value={year}
            data-testid="dashboard-year-select"
            onChange={(e) => setYear(Number(e.target.value))}
            className="bg-[var(--c-card)] border border-[var(--c-border)] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--c-primary)_20%,transparent)]"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {uncategorizedCount > 0 && (
        <Link to="/transactions?filter=uncategorized" className="block">
          <div className="flex items-center gap-3 px-4 py-3 rounded-md bg-[color-mix(in_srgb,var(--c-danger)_8%,transparent)] border border-[color-mix(in_srgb,var(--c-danger)_30%,transparent)] hover:bg-[color-mix(in_srgb,var(--c-danger)_12%,transparent)] transition-colors" data-testid="uncategorized-banner">
            <AlertCircle className="w-5 h-5 text-[var(--c-danger)]" />
            <div className="text-sm">
              <span className="font-medium">{uncategorizedCount}</span> uncategorized transactions need your attention.
              <span className="text-[var(--c-danger)] ml-2 underline">Categorize now →</span>
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
            <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none hover:-translate-y-0.5 hover:shadow-md hover:border-[var(--c-accent)] transition-all duration-300">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--c-muted)]">{s.label}</p>
                  <p className="text-2xl font-semibold mt-2" style={{ fontFamily: "Work Sans" }}>{s.value}</p>
                  <p className="text-xs text-[var(--c-muted)] mt-1">{s.sub}</p>
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

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Monthly cashflow</h3>
              <p className="text-xs text-[var(--c-muted)] mt-0.5">Income vs expense, {year}</p>
            </div>
          </div>
          <div className="h-72" data-testid="monthly-cashflow-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={tc["c-border"]} vertical={false} />
                <XAxis dataKey="month" stroke={tc["c-muted"]} fontSize={12} />
                <YAxis stroke={tc["c-muted"]} fontSize={12} />
                <Tooltip
                  formatter={(v) => formatGBP(v)}
                  contentStyle={{ background: tc["c-card"], border: `1px solid ${tc["c-border"]}`, borderRadius: 6, color: tc["c-ink"] }}
                />
                <Legend />
                <Bar dataKey="Income" fill={tc["c-success"]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Expense" fill={tc["c-danger"]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Expense breakdown</h3>
          <p className="text-xs text-[var(--c-muted)] mt-0.5 mb-4">Top expense categories</p>
          {expenseCategories.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-sm text-[var(--c-muted)]">
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
                      <Cell key={entry.name || `slice-${i}`} fill={entry.color || COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => formatGBP(v)} contentStyle={{ background: tc["c-card"], border: `1px solid ${tc["c-border"]}`, borderRadius: 6, color: tc["c-ink"] }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="mt-3 space-y-1.5 max-h-32 overflow-auto scrollbar-thin">
            {expenseCategories.slice(0, 6).map((c, i) => (
              <div key={c.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: c.color || COLORS[i % COLORS.length] }} />
                  <span className="truncate text-[var(--c-ink)]">{c.name}</span>
                </div>
                <span className="text-[var(--c-muted)]">{formatGBP(c.value)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Budget summary */}
      <BudgetSummary projectId={active.id} year={year} month={new Date().getMonth() + 1} />

      {/* Recent transactions */}
      <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Recent transactions</h3>
            <p className="text-xs text-[var(--c-muted)] mt-0.5">Last imported items</p>
          </div>
          <div className="flex gap-2">
            <Link to="/upload">
              <Button variant="outline" className="border-[var(--c-border)] hover:bg-[var(--c-surface)]" data-testid="dash-upload-btn">
                <Upload className="w-4 h-4 mr-2" /> Upload
              </Button>
            </Link>
            <Link to="/categories">
              <Button variant="outline" className="border-[var(--c-border)] hover:bg-[var(--c-surface)]" data-testid="dash-categories-btn">
                <Tags className="w-4 h-4 mr-2" /> Categories
              </Button>
            </Link>
          </div>
        </div>
        {recent.length === 0 ? (
          <div className="py-12 text-center text-[var(--c-muted)]">
            No transactions yet. Upload a bank statement to begin.
          </div>
        ) : (
          <div className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--c-muted)] border-b border-[var(--c-border)]">
                  <th className="py-3 font-medium">Date</th>
                  <th className="py-3 font-medium">Description</th>
                  <th className="py-3 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id} className="border-b border-[color-mix(in_srgb,var(--c-border)_50%,transparent)]">
                    <td className="py-3 text-[var(--c-muted)]">{t.date}</td>
                    <td className="py-3 truncate max-w-md">{t.description}</td>
                    <td className={`py-3 text-right font-medium ${t.amount >= 0 ? "text-[var(--c-success)]" : "text-[var(--c-danger)]"}`}>
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
