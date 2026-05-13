import React, { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from "react";
import api from "./api";

const ProjectContext = createContext(null);

const ACTIVE_KEY = "activeProjectId";

export const ProjectProvider = ({ children }) => {
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveIdState] = useState(() => localStorage.getItem(ACTIVE_KEY) || null);
  const [loading, setLoading] = useState(true);
  // Bumped on every project switch / delete / window-focus refresh — pages can
  // include this in their useEffect dependency to force a re-fetch without
  // relying on the identity of `active` (which can be stable across changes
  // when the projects array is replaced).
  const [revision, setRevision] = useState(0);
  // Latest activeId, available inside async callbacks without stale closures.
  const activeIdRef = useRef(activeId);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);

  const setActiveId = useCallback((id) => {
    setActiveIdState((prev) => {
      if (prev === id) return prev;
      setRevision((r) => r + 1);
      return id;
    });
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/projects");
      const list = res.data || [];
      setProjects(list);
      const current = activeIdRef.current;
      if (!current && list.length > 0) {
        setActiveId(list[0].id);
      } else if (current && !list.find((p) => p.id === current)) {
        setActiveId(list[0]?.id || null);
      }
      return list;
    } finally {
      setLoading(false);
    }
  }, [setActiveId]);

  // Initial load
  useEffect(() => {
    reload();
  }, [reload]);

  // Persist activeId; clear when null so the next launch falls back cleanly.
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
    else localStorage.removeItem(ACTIVE_KEY);
  }, [activeId]);

  // Refresh the project list when the user comes back to the window — covers
  // the "data went stale while I was on another app" pattern.
  useEffect(() => {
    const onFocus = () => {
      reload();
      setRevision((r) => r + 1);
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [reload]);

  // Force every consumer to re-fetch immediately (used after destructive ops
  // like delete / upload / bulk-categorise that change data outside the page).
  const bumpRevision = useCallback(() => setRevision((r) => r + 1), []);

  // `active` is memoised on identity-stable inputs so consumers that depend on
  // `active` directly don't fire spurious useEffects every render.
  const active = useMemo(
    () => projects.find((p) => p.id === activeId) || null,
    [projects, activeId],
  );

  const value = useMemo(
    () => ({ projects, active, activeId, setActiveId, reload, loading, revision, bumpRevision }),
    [projects, active, activeId, setActiveId, reload, loading, revision, bumpRevision],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
};

export const useProject = () => useContext(ProjectContext);
