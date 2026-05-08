import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useProject } from "../lib/projectContext";
import api from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { UploadCloud, FileText, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function Upload() {
  const { active } = useProject();
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  if (!active) return <div className="text-[#656C5A]">Create or select a project first.</div>;

  const upload = async (file) => {
    if (!file) return;
    const okExt = /\.(csv|pdf)$/i.test(file.name);
    if (!okExt) {
      toast.error("Only CSV or PDF files are supported");
      return;
    }
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
          Drop a CSV or PDF statement. We'll auto-detect dates, descriptions and amounts. Duplicate transactions are skipped automatically.
        </p>
      </div>

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
              <p className="mt-4 text-[#1F2E1B]">Parsing statement... this can take a moment for large PDFs.</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 mx-auto rounded-md bg-[#F4EBE1] flex items-center justify-center">
                <UploadCloud className="w-8 h-8 text-[#364C2E]" />
              </div>
              <h3 className="text-lg mt-4 font-medium" style={{ fontFamily: "Work Sans" }}>
                Drop your CSV or PDF here
              </h3>
              <p className="text-sm text-[#656C5A] mt-1">or click to browse</p>
              <input
                ref={fileRef}
                type="file"
                data-testid="file-input"
                className="hidden"
                accept=".csv,.pdf"
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

      {result && (
        <Card className="p-6 bg-white border-[#EAE3D9] shadow-none" data-testid="upload-result">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-[#4B6B40]" />
            <div>
              <h3 className="font-medium" style={{ fontFamily: "Work Sans" }}>Upload complete</h3>
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
          <li>CSV with columns like Date, Description, Amount (or Debit/Credit)</li>
          <li>PDF statements with tabular transaction lists</li>
          <li>Most UK banks (Lloyds, Barclays, HSBC, Nationwide, Monzo, Starling) work out of the box</li>
        </ul>
      </Card>
    </div>
  );
}
