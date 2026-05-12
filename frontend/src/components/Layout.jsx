import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Receipt, Tags, Upload, BarChart3, Wallet, Plus, ChevronDown, Trash2, Repeat, Settings as SettingsIcon, Target } from "lucide-react";
import BankAccountFilter from "./BankAccountFilter";
import { useProject } from "../lib/projectContext";
import { useConfirm } from "./ConfirmDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";
import api from "../lib/api";
import { toast } from "sonner";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/transactions", label: "Transactions", icon: Receipt },
  { to: "/categories", label: "Categories", icon: Tags },
  { to: "/budgets", label: "Budgets", icon: Target },
  { to: "/reports", label: "Yearly Report", icon: BarChart3 },
  { to: "/recurring", label: "Recurring", icon: Repeat },
  { to: "/upload", label: "Upload Statement", icon: Upload },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function Layout({ children, onNewProject }) {
  const { projects, active, setActiveId, reload } = useProject();
  const navigate = useNavigate();
  const confirm = useConfirm();

  const handleDelete = async () => {
    if (!active) return;
    // Defer the confirm() call so the DropdownMenu can finish its
    // onCloseAutoFocus cycle. Otherwise Radix's body[pointer-events:none] lock
    // from the closing menu portal leaks into the new ConfirmDialog and its
    // buttons silently refuse clicks.
    setTimeout(async () => {
      const ok = await confirm({
        title: `Delete project "${active.name}"?`,
        body: "This permanently removes all transactions, categories and rules in this project. This cannot be undone.",
        confirmLabel: "Delete project",
      });
      if (!ok) return;
      try {
        await api.delete(`/projects/${active.id}`);
        toast.success("Project deleted");
        await reload();
        navigate("/");
      } catch {
        toast.error("Failed to delete");
      }
    }, 80);
  };

  return (
    <div className="min-h-screen flex bg-[#FDFBF7] text-[#1F2E1B]">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-[#EAE3D9] bg-[#FDFBF7] flex flex-col">
        <div className="h-16 flex items-center gap-3 px-6 border-b border-[#EAE3D9]">
          <div className="w-9 h-9 rounded-md bg-[#364C2E] flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-semibold tracking-tight" style={{ fontFamily: "Work Sans" }}>Ledgerly</div>
            <div className="text-xs text-[#656C5A] -mt-0.5">Personal finance</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-6 space-y-1" data-testid="sidebar-nav">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-200 ${
                  isActive
                    ? "bg-[#364C2E] text-white"
                    : "text-[#1F2E1B] hover:bg-[#F4EBE1]"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#EAE3D9]">
          <p className="text-xs text-[#656C5A] uppercase tracking-[0.18em]">Tip</p>
          <p className="text-xs text-[#656C5A] mt-2 leading-relaxed">
            Upload a CSV or PDF to auto-classify recurring merchants.
          </p>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-16 flex items-center justify-between px-8 border-b border-[#EAE3D9] bg-[#FDFBF7] sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <span className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Project</span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  data-testid="project-switcher"
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-[#F4EBE1] transition-colors text-sm font-medium"
                >
                  {active ? active.name : "No project"}
                  <ChevronDown className="w-4 h-4 text-[#656C5A]" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel>Switch project</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {projects.map((p) => (
                  <DropdownMenuItem
                    key={p.id}
                    data-testid={`project-option-${p.id}`}
                    onClick={() => setActiveId(p.id)}
                  >
                    <span className={p.id === active?.id ? "font-semibold" : ""}>{p.name}</span>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onNewProject} data-testid="new-project-menu">
                  <Plus className="w-4 h-4 mr-2" /> New project
                </DropdownMenuItem>
                {active && (
                  <DropdownMenuItem onClick={handleDelete} className="text-[#D96C4E]" data-testid="delete-project-menu">
                    <Trash2 className="w-4 h-4 mr-2" /> Delete current
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <Button
            onClick={onNewProject}
            data-testid="header-new-project-btn"
            className="bg-[#364C2E] hover:bg-[#22331D] text-white rounded-md font-medium"
          >
            <Plus className="w-4 h-4 mr-1.5" /> New Project
          </Button>
        </header>

        <div className="px-8 pt-4 flex items-center gap-3 flex-wrap">
          <BankAccountFilter />
        </div>

        <main className="flex-1 px-8 pt-4 pb-24 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
