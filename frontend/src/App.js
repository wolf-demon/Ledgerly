import React, { useState } from "react";
import "@/App.css";
import "@/index.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ProjectProvider } from "./lib/projectContext";
import Layout from "./components/Layout";
import NewProjectDialog from "./components/NewProjectDialog";
import { useProject } from "./lib/projectContext";

import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Categories from "./pages/Categories";
import Upload from "./pages/Upload";
import Reports from "./pages/Reports";

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
        <Route path="/upload" element={<Upload />} />
      </Routes>
      <NewProjectDialog open={open} onOpenChange={setOpen} onCreated={handleCreated} />
    </Layout>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <ProjectProvider>
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
        </ProjectProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
