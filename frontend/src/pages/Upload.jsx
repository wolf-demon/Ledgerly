import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useProject } from "../lib/projectContext";
import api from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { UploadCloud, FileText, Loader2, CheckCircle2, Link as LinkIcon, ExternalLink } from "lucide-react";
import { toast } from "sonner";

const SUPPORTED_EXT = ".csv,.tsv,.pdf,.xlsx,.xls,.ods,.ofx,.qfx";

export default function Upload() {
  const { active } = useProject();
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [sheetUrl, setSheetUrl] = useState("");

  if (!active) return <div className="text-[#656C5A]">Create or select a project first.</div>;

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("project_id", active.id);
      fd.append("file", file);
      const res = await api.post("/transactions/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
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
      toast.success(`Imported ${res.data.inserted} transactions from ${res.data.source || "URL"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import failed");
    } finally {
      setBusy(false);
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
        <p className="text-xs uppercase tracking-[0.2em] text-[#656C5A]">Import</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
          Upload bank statement
        </h1>
        <p className="text-[#656C5A] mt-2 text-sm leading-relaxed">
          Drop a file or paste a Google Sheets link. We auto-detect dates, descriptions and amounts. Duplicates are skipped automatically.
        </p>
      </div>

      <Tabs defaultValue="file">
        <TabsList className="bg-[#F4EBE1]">
          <TabsTrigger value="file" data-testid="upload-tab-file">
            <UploadCloud className="w-4 h-4 mr-1.5" /> Upload file
          </TabsTrigger>
          <TabsTrigger value="url" data-testid="upload-tab-url">
            <LinkIcon className="w-4 h-4 mr-1.5" /> Google Sheets / URL
          </TabsTrigger>
        </TabsList>

        <TabsContent value="file" className="mt-5">
          <Card
            className={`border-2 border-dashed bg-white transition-all ${
              dragOver ? "border-[#364C2E] bg-[#F4EBE1]/40" : "border-[#EAE3D9]"
            } shadow-none`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            data-testid="upload-dropzone"
          >
            <div className="p-12 text-center">
              {busy ? (
                <>
                  <Loader2 className="w-10 h-10 mx-auto text-[#364C2E] animate-spin" />
                  <p className="mt-4 text-[#1F2E1B]">Parsing statement...</p>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 mx-auto rounded-md bg-[#F4EBE1] flex items-center justify-center">
                    <UploadCloud className="w-8 h-8 text-[#364C2E]" />
                  </div>
                  <h3 className="text-lg mt-4 font-medium" style={{ fontFamily: "Work Sans" }}>
                    Drop a CSV, Excel, PDF, ODS or OFX here
                  </h3>
                  <p className="text-sm text-[#656C5A] mt-1">or click to browse</p>
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
                    className="mt-6 bg-[#364C2E] hover:bg-[#22331D] text-white"
                  >
                    <FileText className="w-4 h-4 mr-2" /> Choose file
                  </Button>
                </>
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="url" className="mt-5">
          <Card className="p-6 bg-white border-[#EAE3D9] shadow-none">
            <Label htmlFor="sheet-url" className="text-sm">Google Sheets share link or public CSV/Excel URL</Label>
            <div className="flex gap-2 mt-2">
              <Input
                id="sheet-url"
                data-testid="sheet-url-input"
                placeholder="https://docs.google.com/spreadsheets/d/..../edit"
                value={sheetUrl}
                onChange={(e) => setSheetUrl(e.target.value)}
                className="bg-white border-[#EAE3D9] flex-1"
              />
              <Button
                onClick={importUrl}
                disabled={busy}
                data-testid="import-url-btn"
                className="bg-[#364C2E] hover:bg-[#22331D] text-white whitespace-nowrap"
              >
                {busy ? (<><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Fetching…</>) : (<>Import</>)}
              </Button>
            </div>
            <div className="mt-4 p-3 rounded-md bg-[#F4EBE1]/40 border border-[#EAE3D9] text-xs text-[#656C5A]">
              <p className="font-medium text-[#1F2E1B] mb-1">For Google Sheets to work:</p>
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
        <Card className="p-6 bg-white border-[#EAE3D9] shadow-none" data-testid="upload-result">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-[#4B6B40]" />
            <div>
              <h3 className="font-medium" style={{ fontFamily: "Work Sans" }}>Import complete</h3>
              <p className="text-sm text-[#656C5A] mt-0.5">
                {result.inserted} new transactions imported, {result.skipped} duplicates skipped (of {result.total} parsed).
              </p>
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <Button onClick={() => navigate("/transactions?filter=uncategorized")} className="bg-[#364C2E] hover:bg-[#22331D] text-white" data-testid="goto-uncategorized-btn">
              Categorize transactions
            </Button>
            <Button onClick={() => navigate("/")} variant="outline" className="border-[#EAE3D9] hover:bg-[#F4EBE1]" data-testid="goto-dashboard-btn">
              View dashboard
            </Button>
          </div>
        </Card>
      )}

      <Card className="p-6 bg-[#F4EBE1]/40 border-[#EAE3D9] shadow-none">
        <h4 className="font-medium" style={{ fontFamily: "Work Sans" }}>Supported formats</h4>
        <ul className="text-sm text-[#656C5A] mt-2 space-y-1 list-disc pl-5">
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
