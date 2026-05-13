import React, { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from "react";
import api from "./api";
import { useProject } from "./projectContext";

const BankAccountContext = createContext({
  accounts: [],
  selectedId: null,
  setSelectedId: () => {},
  reload: () => {},
});

const STORAGE_PREFIX = "ledgerly.bankFilter:";

export function BankAccountProvider({ children }) {
  const { active, revision } = useProject();
  const [accounts, setAccounts] = useState([]);
  const [selectedId, setSelectedIdState] = useState(null);
  // Guard against stale fetches when the user switches project quickly: only
  // accept the response whose request-epoch matches the latest one.
  const fetchEpoch = useRef(0);

  const reload = useCallback(async () => {
    if (!active) {
      setAccounts([]);
      return;
    }
    const epoch = ++fetchEpoch.current;
    try {
      const r = await api.get("/bank-accounts", { params: { project_id: active.id } });
      // Drop the response if another fetch has started after us.
      if (epoch !== fetchEpoch.current) return;
      setAccounts(r.data);
    } catch {
      if (epoch !== fetchEpoch.current) return;
      setAccounts([]);
    }
  }, [active]);

  // When the active project switches, clear the previous project's accounts +
  // selection IMMEDIATELY (no flash of stale data), then load fresh.
  useEffect(() => {
    fetchEpoch.current++; // invalidate any in-flight fetch
    setAccounts([]);
    if (!active) {
      setSelectedIdState(null);
      return;
    }
    const stored = localStorage.getItem(STORAGE_PREFIX + active.id);
    setSelectedIdState(stored || null);
    reload();
  }, [active, reload, revision]);

  const setSelectedId = useCallback((id) => {
    setSelectedIdState(id);
    if (active) {
      if (id) localStorage.setItem(STORAGE_PREFIX + active.id, id);
      else localStorage.removeItem(STORAGE_PREFIX + active.id);
    }
  }, [active]);

  // Drop the selection if the chosen account no longer exists — but ONLY once
  // the accounts list has been refreshed for the current project (otherwise
  // we'd wipe the stored selection during the brief window between project
  // switch and the first successful /bank-accounts response).
  useEffect(() => {
    if (selectedId && accounts.length > 0 && !accounts.some((a) => a.id === selectedId)) {
      setSelectedId(null);
    }
  }, [accounts, selectedId, setSelectedId]);

  const value = useMemo(() => ({
    accounts,
    selectedId,
    setSelectedId,
    reload,
    selected: accounts.find((a) => a.id === selectedId) || null,
  }), [accounts, selectedId, setSelectedId, reload]);

  return <BankAccountContext.Provider value={value}>{children}</BankAccountContext.Provider>;
}

export function useBankAccount() {
  return useContext(BankAccountContext);
}
