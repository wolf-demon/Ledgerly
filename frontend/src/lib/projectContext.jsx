import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";

const ProjectContext = createContext(null);

export const ProjectProvider = ({ children }) => {
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState(() => localStorage.getItem("activeProjectId") || null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/projects");
      setProjects(res.data || []);
      if (!activeId && res.data && res.data.length > 0) {
        setActiveId(res.data[0].id);
      }
      if (activeId && res.data && !res.data.find((p) => p.id === activeId)) {
        setActiveId(res.data[0]?.id || null);
      }
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeId) localStorage.setItem("activeProjectId", activeId);
  }, [activeId]);

  const active = projects.find((p) => p.id === activeId) || null;

  return (
    <ProjectContext.Provider value={{ projects, active, activeId, setActiveId, reload, loading }}>
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => useContext(ProjectContext);
