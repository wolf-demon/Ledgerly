import React, { useState } from "react";
import "@/App.css";
import "@/index.css";
import { BrowserRouter, HashRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ProjectProvider } from "./lib/projectContext";
import { BankAccountProvider } from "./lib/bankAccountContext";
import { ConfirmProvider } from "./components/ConfirmDialog";
import Layout from "./components/Layout";
import NewProjectDialog from "./components/NewProjectDialog";
import { useProject } from "./lib/projectContext";

import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Categories from "./pages/Categories";
import Upload from "./pages/Upload";
import Reports from "./pages/Reports";
import Recurring from "./pages/Recurring";
import Settings from "./pages/Settings";
import Budgets from "./pages/Budgets";

// In Electron the app is served via the file:// protocol, where BrowserRouter's
// HTML5 history API breaks. Switch to HashRouter automatically in that case.
const Router =
  typeof window !== "undefined" && window.location.protocol === "file:"
    ? HashRouter
    : BrowserRouter;

function Shell() {
  const [open, setOpen] = useState(false);
  const { reload, setActiveId } = useProject();

  const handleCreated = (proj) => {
    reload();
    setActiveId(proj.id);
  };

  return (
    <Layout onNewProject={() => setOpen(true)}>
      <Routes>
        <Route path="/" element={<Dashboard onNewProject={() => setOpen(true)} />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/recurring" element={<Recurring />} />
        <Route path="/budgets" element={<Budgets />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
      <NewProjectDialog open={open} onOpenChange={setOpen} onCreated={handleCreated} />
    </Layout>
  );
}

function App() {
  return (
    <div className="App">
      <Router>
        <ProjectProvider>
          <BankAccountProvider>
            <ConfirmProvider>
              <Shell />
              <Toaster
                position="top-right"
                toastOptions={{
                  style: {
                    background: "#FFFFFF",
                    border: "1px solid #EAE3D9",
                    color: "#1F2E1B",
                  },
                }}
              />
            </ConfirmProvider>
          </BankAccountProvider>
        </ProjectProvider>
      </Router>
    </div>
  );
}

export default App;
