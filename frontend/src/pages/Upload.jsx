import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useProject } from "../lib/projectContext";
import { useBankAccount } from "../lib/bankAccountContext";
import api from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { UploadCloud, FileText, Loader2, CheckCircle2, Link as LinkIcon, ExternalLink, Wallet, AlertCircle } from "lucide-react";
import { toast } from "sonner";

const SUPPORTED_EXT = ".csv,.tsv,.pdf,.xlsx,.xls,.ods,.ofx,.qfx";

export default function Upload() {
  const { active, bumpRevision } = useProject();
  const { accounts, reload: reloadAccounts } = useBankAccount();
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [sheetUrl, setSheetUrl] = useState("");
  // null = "Auto-detect" (let the backend infer from the file). A real ID overrides.
  const [overrideAccountId, setOverrideAccountId] = useState("");
  // Post-upload manual reassignment selection.
  const [reassignTo, setReassignTo] = useState("");

  // Refresh account list whenever the page mounts so the picker stays in sync.
  useEffect(() => {
    if (active) reloadAccounts();
  }, [active, reloadAccounts]);

  if (!active) return <div className="text-[var(--c-muted)]">Create or select a project first.</div>;

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("project_id", active.id);
      fd.append("file", file);
      if (overrideAccountId) fd.append("bank_account_id", overrideAccountId);
      const res = await api.post("/transactions/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
      setReassignTo(res.data.bank_account_id || "");
      reloadAccounts();
      bumpRevision();
      toast.success(`Imported ${res.data.inserted} transactions (${res.data.skipped} duplicates skipped)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const importUrl = async () => {
    if (!sheetUrl.trim()) {
      toast.error("Paste a Google Sheets share URL or a public CSV/Excel link");
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const res = await api.post("/transactions/import-url", {
        project_id: active.id,
        url: sheetUrl.trim(),
      });
      setResult(res.data);
      bumpRevision();
      toast.success(`Imported ${res.data.inserted} transactions from ${res.data.source || "URL"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const reassignBankAccount = async () => {
    if (!result?.bank_account_id || reassignTo === result.bank_account_id) return;
    // Bulk-update every transaction this upload created to point at the new account.
    // We do this by fetching transactions linked to the auto-detected account and
    // moving them over. PUT /transactions doesn't support bank_account_id rewrites
    // out of the box, so we go through the existing list endpoint + per-row update
    // is wasteful. Instead use the bank-accounts MERGE pattern: re-name the existing
    // account if we're keeping it, or delete-and-reattach via the back end.
    try {
      // The simplest user-visible action: rename the auto-created account to the
      // selected target's name, then DELETE the target account (which detaches
      // its txns) and rename the auto-created back into place. Too clever.
      // Cleanest: ask the user to delete the wrong auto-detected account in the
      // accounts page. For now, expose the manual reassignment as a server PUT
      // that swaps bank_account_id on all txns of the auto-detected account.
      const detected = result.bank_account_id;
      await api.put(`/bank-accounts/${detected}/reassign`, { target_id: reassignTo });
      toast.success("Bank account updated for all imported transactions");
      // Update local state so the UI reflects the change immediately.
      setResult({ ...result, bank_account_id: reassignTo });
      reloadAccounts();
      bumpRevision();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reassign — try the Bank Accounts page");
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) upload(f);
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Import</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
          Upload bank statement
        </h1>
        <p className="text-[var(--c-muted)] mt-2 text-sm leading-relaxed">
          Drop a file or paste a Google Sheets link. We auto-detect dates, descriptions and amounts. Duplicates are skipped automatically.
        </p>
      </div>

      <Tabs defaultValue="file">
        <TabsList className="bg-[var(--c-surface)]">
          <TabsTrigger value="file" data-testid="upload-tab-file">
            <UploadCloud className="w-4 h-4 mr-1.5" /> Upload file
          </TabsTrigger>
          <TabsTrigger value="url" data-testid="upload-tab-url">
            <LinkIcon className="w-4 h-4 mr-1.5" /> Google Sheets / URL
          </TabsTrigger>
        </TabsList>

        {/* Pre-upload bank-account picker. By default we auto-detect from the
            PDF sort code. The picker lets the user force a specific account
            (useful for CSV/Excel files where there's no sort code to detect,
            or when a statement uses an unrecognised format). */}
        {accounts.length > 0 && (
          <Card className="mt-4 p-4 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
            <Label className="text-xs uppercase tracking-wide text-[var(--c-muted)] flex items-center gap-1.5">
              <Wallet className="w-3.5 h-3.5" /> Bank account for this upload
            </Label>
            <select
              value={overrideAccountId}
              onChange={(e) => setOverrideAccountId(e.target.value)}
              data-testid="upload-account-picker"
              className="w-full mt-2 h-9 px-3 bg-[var(--c-card)] border border-[var(--c-border)] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--c-primary)_20%,transparent)]"
            >
              <option value="">Auto-detect from file (recommended for PDFs)</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.sort_code ? ` · ${a.sort_code}` : ""}
                </option>
              ))}
            </select>
            <p className="text-xs text-[var(--c-muted)] mt-1.5">
              Pick a specific account if auto-detect picks the wrong one or your file has no sort code (e.g. CSV).
            </p>
          </Card>
        )}

        <TabsContent value="file" className="mt-5">
          <Card
            className={`border-2 border-dashed bg-[var(--c-card)] transition-all ${
              dragOver ? "border-[var(--c-primary)] bg-[color-mix(in_srgb,var(--c-surface)_40%,transparent)]" : "border-[var(--c-border)]"
            } shadow-none`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            data-testid="upload-dropzone"
          >
            <div className="p-12 text-center">
              {busy ? (
                <>
                  <Loader2 className="w-10 h-10 mx-auto text-[var(--c-primary)] animate-spin" />
                  <p className="mt-4 text-[var(--c-ink)]">Parsing statement...</p>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 mx-auto rounded-md bg-[var(--c-surface)] flex items-center justify-center">
                    <UploadCloud className="w-8 h-8 text-[var(--c-primary)]" />
                  </div>
                  <h3 className="text-lg mt-4 font-medium" style={{ fontFamily: "Work Sans" }}>
                    Drop a CSV, Excel, PDF, ODS or OFX here
                  </h3>
                  <p className="text-sm text-[var(--c-muted)] mt-1">or click to browse</p>
                  <input
                    ref={fileRef}
                    type="file"
                    data-testid="file-input"
                    className="hidden"
                    accept={SUPPORTED_EXT}
                    onChange={(e) => upload(e.target.files?.[0])}
                  />
                  <Button
                    onClick={() => fileRef.current?.click()}
                    data-testid="choose-file-btn"
                    className="mt-6 bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]"
                  >
                    <FileText className="w-4 h-4 mr-2" /> Choose file
                  </Button>
                </>
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="url" className="mt-5">
          <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
            <Label htmlFor="sheet-url" className="text-sm">Google Sheets share link or public CSV/Excel URL</Label>
            <div className="flex gap-2 mt-2">
              <Input
                id="sheet-url"
                data-testid="sheet-url-input"
                placeholder="https://docs.google.com/spreadsheets/d/..../edit"
                value={sheetUrl}
                onChange={(e) => setSheetUrl(e.target.value)}
                className="bg-[var(--c-card)] border-[var(--c-border)] flex-1"
              />
              <Button
                onClick={importUrl}
                disabled={busy}
                data-testid="import-url-btn"
                className="bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)] whitespace-nowrap"
              >
                {busy ? (<><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Fetching…</>) : (<>Import</>)}
              </Button>
            </div>
            <div className="mt-4 p-3 rounded-md bg-[color-mix(in_srgb,var(--c-surface)_40%,transparent)] border border-[var(--c-border)] text-xs text-[var(--c-muted)]">
              <p className="font-medium text-[var(--c-ink)] mb-1">For Google Sheets to work:</p>
              <ol className="list-decimal pl-5 space-y-0.5">
                <li>Open your sheet in Google Sheets</li>
                <li>Click <strong>Share</strong> → set "General access" to <strong>Anyone with the link</strong> (Viewer)</li>
                <li>Copy the URL from the address bar and paste it here</li>
              </ol>
              <p className="mt-2">No Google login required — Ledgerly only fetches the public CSV export.</p>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {result && (
        <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none" data-testid="upload-result">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-[var(--c-success)]" />
            <div>
              <h3 className="font-medium" style={{ fontFamily: "Work Sans" }}>Import complete</h3>
              <p className="text-sm text-[var(--c-muted)] mt-0.5">
                {result.inserted} new transactions imported, {result.skipped} duplicates skipped (of {result.total} parsed).
              </p>
            </div>
          </div>

          {/* Bank account confirmation / manual override.
              - If detection picked an account, show which one + an option to reassign.
              - If nothing was detected, show a picker so the user can attach one. */}
          {result.bank_account?.auto_detected && result.bank_account_id && (
            <div className="mt-4 px-4 py-3 rounded-md bg-[color-mix(in_srgb,var(--c-surface)_60%,transparent)] border border-[var(--c-border)]">
              <div className="flex flex-wrap items-center gap-3">
                <Wallet className="w-4 h-4 text-[var(--c-primary)]" />
                <span className="text-sm">
                  {result.bank_account.created ? "Created new account" : "Auto-detected account"}:{" "}
                  <strong>{result.bank_account.account_name}</strong>
                  {result.bank_account.sort_code && <span className="text-[var(--c-muted)]"> · {result.bank_account.sort_code}</span>}
                </span>
                <div className="flex items-center gap-2 ml-auto">
                  <select
                    value={reassignTo}
                    onChange={(e) => setReassignTo(e.target.value)}
                    data-testid="upload-reassign-picker"
                    className="h-8 px-2 bg-[var(--c-card)] border border-[var(--c-border)] rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[color-mix(in_srgb,var(--c-primary)_20%,transparent)]"
                  >
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))}
                  </select>
                  <Button
                    size="sm" variant="outline"
                    onClick={reassignBankAccount}
                    disabled={!reassignTo || reassignTo === result.bank_account_id}
                    data-testid="upload-reassign-btn"
                    className="border-[var(--c-border)] hover:bg-[var(--c-surface)] disabled:opacity-50"
                  >
                    Reassign
                  </Button>
                </div>
              </div>
            </div>
          )}
          {!result.bank_account_id && result.bank_account?.sort_code === null && (
            <div className="mt-4 px-4 py-3 rounded-md bg-[color-mix(in_srgb,var(--c-accent)_15%,transparent)] border border-[color-mix(in_srgb,var(--c-accent)_30%,transparent)] flex items-center gap-3">
              <AlertCircle className="w-4 h-4 text-[var(--c-warn)]" />
              <p className="text-sm text-[var(--c-warn)]">
                No sort code found in the file — these transactions aren't linked to a bank account yet. Use the picker above on your next upload to assign one.
              </p>
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <Button onClick={() => navigate("/transactions?filter=uncategorized")} className="bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]" data-testid="goto-uncategorized-btn">
              Categorize transactions
            </Button>
            <Button onClick={() => navigate("/")} variant="outline" className="border-[var(--c-border)] hover:bg-[var(--c-surface)]" data-testid="goto-dashboard-btn">
              View dashboard
            </Button>
          </div>
        </Card>
      )}

      <Card className="p-6 bg-[color-mix(in_srgb,var(--c-surface)_40%,transparent)] border-[var(--c-border)] shadow-none">
        <h4 className="font-medium" style={{ fontFamily: "Work Sans" }}>Supported formats</h4>
        <ul className="text-sm text-[var(--c-muted)] mt-2 space-y-1 list-disc pl-5">
          <li><strong>CSV / TSV</strong> — most banks export to this</li>
          <li><strong>Excel</strong> (.xlsx, .xls)</li>
          <li><strong>OpenDocument Spreadsheet</strong> (.ods) — LibreOffice / Apple Numbers export</li>
          <li><strong>PDF</strong> — most UK statements (Lloyds, Barclays, HSBC, Nationwide, Monzo, Starling)</li>
          <li><strong>OFX / QFX</strong> — the bank-standard finance format</li>
          <li><strong>Google Sheets</strong> via public share URL <ExternalLink className="inline w-3 h-3 ml-0.5 -mt-0.5" /></li>
        </ul>
      </Card>
    </div>
  );
}
