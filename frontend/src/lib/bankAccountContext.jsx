import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
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
  const { active } = useProject();
  const [accounts, setAccounts] = useState([]);
  const [selectedId, setSelectedIdState] = useState(null);

  const reload = useCallback(async () => {
    if (!active) {
      setAccounts([]);
      return;
    }
    try {
      const r = await api.get("/bank-accounts", { params: { project_id: active.id } });
      setAccounts(r.data);
    } catch {
      setAccounts([]);
    }
  }, [active]);

  // Restore the per-project selection from localStorage when the active project switches.
  useEffect(() => {
    if (!active) {
      setSelectedIdState(null);
      return;
    }
    const stored = localStorage.getItem(STORAGE_PREFIX + active.id);
    setSelectedIdState(stored || null);
    reload();
  }, [active, reload]);

  const setSelectedId = useCallback((id) => {
    setSelectedIdState(id);
    if (active) {
      if (id) localStorage.setItem(STORAGE_PREFIX + active.id, id);
      else localStorage.removeItem(STORAGE_PREFIX + active.id);
    }
  }, [active]);

  // Drop the selection if the chosen account no longer exists.
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
