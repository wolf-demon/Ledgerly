import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Cloud, Server, Power, ExternalLink, CheckCircle2, AlertCircle, Loader2, Wand2, Copy, Eye, EyeOff, Palette } from "lucide-react";
import { toast } from "sonner";
import { useTheme } from "../lib/themeContext";

const PROVIDERS = [
  {
    key: "emergent",
    title: "Emergent (cloud)",
    icon: Cloud,
    desc: "Uses Claude Sonnet 4.5 via Emergent's hosted key. Highest accuracy. Sends transaction descriptions to the cloud.",
  },
  {
    key: "ollama",
    title: "Ollama (local)",
    icon: Server,
    desc: "Runs entirely on your machine. Private, free, offline. Requires installing Ollama and pulling a model.",
  },
  {
    key: "none",
    title: "Disabled",
    icon: Power,
    desc: "No AI suggestions. You'll categorize transactions manually.",
  },
];

const platformInstall = () => {
  const ua = (typeof navigator !== "undefined" ? navigator.userAgent : "").toLowerCase();
  if (ua.includes("mac")) return { os: "macOS", cmd: "brew install ollama   # or download from ollama.com/download" };
  if (ua.includes("win")) return { os: "Windows", cmd: "Download installer from ollama.com/download" };
  return { os: "Linux", cmd: "curl -fsSL https://ollama.com/install.sh | sh" };
};

export default function Settings() {
  const { theme, setTheme, themes } = useTheme();
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [showKey, setShowKey] = useState(false);
  const [emergentTesting, setEmergentTesting] = useState(false);
  const [emergentResult, setEmergentResult] = useState(null);

  useEffect(() => {
    api.get("/settings").then((r) => {
      setSettings(r.data);
      setLoading(false);
    });
  }, []);

  if (loading || !settings) {
    return <div className="text-[var(--c-muted)]">Loading settings...</div>;
  }

  const update = (patch) => setSettings((s) => ({ ...s, ...patch }));

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.put("/settings", settings);
      setSettings(res.data);
      toast.success("Settings saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const testOllama = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post("/settings/test-ollama", {
        ollama_url: settings.ollama_url,
        ollama_model: settings.ollama_model,
      });
      setTestResult(res.data);
      if (res.data.reachable) {
        const hasModel = (res.data.models || []).some((m) =>
          m === settings.ollama_model || m.startsWith(`${settings.ollama_model}:`)
        );
        if (hasModel) toast.success("Ollama is running and the selected model is installed.");
        else toast.warning(`Ollama is running but '${settings.ollama_model}' is not pulled yet.`);
      } else {
        toast.error("Ollama is not reachable.");
      }
    } catch {
      toast.error("Test failed");
    } finally {
      setTesting(false);
    }
  };

  const testEmergent = async () => {
    setEmergentTesting(true);
    setEmergentResult(null);
    try {
      const res = await api.post("/settings/test-emergent", {
        emergent_key: settings.emergent_key || "",
      });
      setEmergentResult(res.data);
      if (res.data.reachable) toast.success("Emergent key is working.");
      else toast.error("Emergent key test failed.");
    } catch {
      toast.error("Test failed");
    } finally {
      setEmergentTesting(false);
    }
  };

  const copyCmd = (cmd) => {
    navigator.clipboard?.writeText(cmd);
    toast.success("Copied");
  };

  const inst = platformInstall();
  const pullCmd = `ollama pull ${settings.ollama_model}`;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--c-muted)]">Configuration</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-1" style={{ fontFamily: "Work Sans" }}>
          Settings
        </h1>
        <p className="text-[var(--c-muted)] mt-1 text-sm">Pick how Ledgerly should suggest categories for new transactions.</p>
      </div>

      {/* Theme picker */}
      <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none ledger-fade-in">
        <div className="flex items-center gap-2 mb-1">
          <Palette className="w-4 h-4 text-[var(--c-primary)]" />
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Theme</h3>
        </div>
        <p className="text-xs text-[var(--c-muted)] mb-4">Customise the look of Ledgerly. Your choice is remembered on this device.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="theme-grid">
          {themes.map((t) => {
            const active = theme === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTheme(t.id)}
                data-testid={`theme-${t.id}`}
                className={`text-left p-4 rounded-md border-2 transition-all hover:-translate-y-0.5 ${
                  active
                    ? "border-[var(--c-primary)] bg-[color-mix(in_srgb,var(--c-primary)_5%,transparent)]"
                    : "border-[var(--c-border)] hover:border-[var(--c-accent)] bg-[var(--c-card)]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--c-ink)]">{t.name}</span>
                  <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-[var(--c-surface)] text-[var(--c-muted)]">
                    {t.mode}
                  </span>
                </div>
                <div className="flex gap-1.5 mt-3">
                  {t.swatch.map((hex, i) => (
                    <span
                      key={`${t.id}-${hex}-${i}`}
                      className="w-6 h-6 rounded shadow-sm"
                      style={{ backgroundColor: hex, border: "1px solid rgba(0,0,0,0.06)" }}
                    />
                  ))}
                </div>
                <p className="text-xs text-[var(--c-muted)] mt-3 leading-relaxed">{t.description}</p>
              </button>
            );
          })}
        </div>
      </Card>

      {/* Provider selector */}
      <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none">
        <h3 className="text-lg font-medium mb-4" style={{ fontFamily: "Work Sans" }}>AI provider</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="provider-grid">
          {PROVIDERS.map((p) => {
            const active = settings.ai_provider === p.key;
            return (
              <button
                key={p.key}
                onClick={() => update({ ai_provider: p.key })}
                data-testid={`provider-${p.key}`}
                className={`text-left p-4 rounded-md border-2 transition-all ${
                  active
                    ? "border-[var(--c-primary)] bg-[color-mix(in_srgb,var(--c-primary)_5%,transparent)]"
                    : "border-[var(--c-border)] hover:border-[var(--c-accent)] bg-[var(--c-card)]"
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-8 h-8 rounded-md flex items-center justify-center ${
                    active ? "bg-[var(--c-primary)] text-[var(--c-on-primary)]" : "bg-[var(--c-surface)] text-[var(--c-primary)]"
                  }`}>
                    <p.icon className="w-4 h-4" />
                  </div>
                  <span className="font-medium">{p.title}</span>
                </div>
                <p className="text-xs text-[var(--c-muted)] leading-relaxed">{p.desc}</p>
              </button>
            );
          })}
        </div>
      </Card>

      {/* Emergent key (only when emergent provider) */}
      {settings.ai_provider === "emergent" && (
        <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none" data-testid="emergent-settings">
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Emergent LLM key</h3>
          <p className="text-xs text-[var(--c-muted)] mt-1 mb-5">
            Used to call Claude Sonnet 4.5 via Emergent's hosted proxy. The desktop installer ships with a built-in key,
            so this is only needed if you want to use your own (e.g. for a higher quota).
          </p>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="emergent-key">API key</Label>
              <div className="flex gap-2">
                <Input
                  id="emergent-key"
                  data-testid="emergent-key-input"
                  type={showKey ? "text" : "password"}
                  value={settings.emergent_key || ""}
                  onChange={(e) => update({ emergent_key: e.target.value })}
                  placeholder="sk-emergent-..."
                  className="bg-[var(--c-card)] border-[var(--c-border)] flex-1 font-mono text-sm"
                  autoComplete="off"
                  spellCheck={false}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setShowKey((s) => !s)}
                  data-testid="toggle-key-visibility"
                  className="border-[var(--c-border)] hover:bg-[var(--c-surface)]"
                  aria-label={showKey ? "Hide key" : "Show key"}
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </Button>
              </div>
              <p className="text-xs text-[var(--c-muted)]">
                Get one from{" "}
                <a href="https://app.emergent.sh" target="_blank" rel="noreferrer" className="text-[var(--c-primary)] underline">
                  app.emergent.sh
                </a>
                {" "}→ Profile → Universal Key. Leave blank to use the bundled default.
              </p>
            </div>

            <Button
              type="button"
              onClick={testEmergent}
              disabled={emergentTesting}
              data-testid="test-emergent-btn"
              variant="outline"
              className="border-[var(--c-border)] hover:bg-[var(--c-surface)]"
            >
              {emergentTesting ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Testing...</>) : (<><Wand2 className="w-4 h-4 mr-2" /> Test connection</>)}
            </Button>

            {emergentResult && (
              <div
                className={`p-3 rounded-md text-sm border ${
                  emergentResult.reachable
                    ? "bg-[color-mix(in_srgb,var(--c-success)_10%,transparent)] border-[color-mix(in_srgb,var(--c-success)_30%,transparent)]"
                    : "bg-[color-mix(in_srgb,var(--c-danger)_8%,transparent)] border-[color-mix(in_srgb,var(--c-danger)_30%,transparent)]"
                }`}
                data-testid="emergent-test-result"
              >
                {emergentResult.reachable ? (
                  <div className="flex items-center gap-2 font-medium text-[var(--c-ink)]">
                    <CheckCircle2 className="w-4 h-4 text-[var(--c-success)]" />
                    Key works — responded with: <code className="text-xs">{emergentResult.sample}</code>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 font-medium">
                      <AlertCircle className="w-4 h-4 text-[var(--c-danger)]" />
                      Test failed
                    </div>
                    <div className="text-xs text-[var(--c-muted)] mt-1">{emergentResult.error}</div>
                  </>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Ollama settings (only when ollama is selected) */}
      {settings.ai_provider === "ollama" && (
        <Card className="p-6 bg-[var(--c-card)] border-[var(--c-border)] shadow-none" data-testid="ollama-settings">
          <h3 className="text-lg font-medium" style={{ fontFamily: "Work Sans" }}>Ollama configuration</h3>
          <p className="text-xs text-[var(--c-muted)] mt-1 mb-5">
            Ollama runs locally on your machine. Ledgerly talks to it via its REST API.
          </p>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ollama-url">Ollama server URL</Label>
              <Input
                id="ollama-url"
                data-testid="ollama-url-input"
                value={settings.ollama_url}
                onChange={(e) => update({ ollama_url: e.target.value })}
                placeholder="http://localhost:11434"
                className="bg-[var(--c-card)] border-[var(--c-border)]"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ollama-model">Model name</Label>
              <Input
                id="ollama-model"
                data-testid="ollama-model-input"
                value={settings.ollama_model}
                onChange={(e) => update({ ollama_model: e.target.value })}
                placeholder="llama3.2"
                className="bg-[var(--c-card)] border-[var(--c-border)]"
              />
              <p className="text-xs text-[var(--c-muted)]">
                Recommended: <code className="bg-[var(--c-surface)] px-1.5 py-0.5 rounded">llama3.2</code> (3 GB), <code className="bg-[var(--c-surface)] px-1.5 py-0.5 rounded">qwen2.5:7b</code>, or <code className="bg-[var(--c-surface)] px-1.5 py-0.5 rounded">mistral</code>. Smaller = faster but less accurate.
              </p>
            </div>

            <Button
              type="button"
              onClick={testOllama}
              disabled={testing}
              data-testid="test-ollama-btn"
              variant="outline"
              className="border-[var(--c-border)] hover:bg-[var(--c-surface)]"
            >
              {testing ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Testing...</>) : (<><Wand2 className="w-4 h-4 mr-2" /> Test connection</>)}
            </Button>

            {testResult && (
              <div
                className={`p-3 rounded-md text-sm border ${
                  testResult.reachable
                    ? "bg-[color-mix(in_srgb,var(--c-success)_10%,transparent)] border-[color-mix(in_srgb,var(--c-success)_30%,transparent)] text-[var(--c-ink)]"
                    : "bg-[color-mix(in_srgb,var(--c-danger)_8%,transparent)] border-[color-mix(in_srgb,var(--c-danger)_30%,transparent)] text-[var(--c-ink)]"
                }`}
                data-testid="test-result"
              >
                {testResult.reachable ? (
                  <>
                    <div className="flex items-center gap-2 font-medium">
                      <CheckCircle2 className="w-4 h-4 text-[var(--c-success)]" />
                      Ollama is reachable
                    </div>
                    <div className="text-xs text-[var(--c-muted)] mt-1">
                      Installed models: {testResult.models?.length ? testResult.models.join(", ") : "none yet"}
                    </div>
                    {testResult.models?.length > 0 && !testResult.models.some((m) => m === settings.ollama_model || m.startsWith(`${settings.ollama_model}:`)) && (
                      <div className="text-xs mt-2">
                        Run this in your terminal to install the model:
                        <div className="mt-1 flex items-center gap-2">
                          <code className="bg-[var(--c-ink)] text-[var(--c-bg)] px-2 py-1 rounded text-xs flex-1">{pullCmd}</code>
                          <Button size="sm" variant="ghost" onClick={() => copyCmd(pullCmd)} data-testid="copy-pull-cmd">
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2 font-medium">
                      <AlertCircle className="w-4 h-4 text-[var(--c-danger)]" />
                      Ollama is not reachable
                    </div>
                    <div className="text-xs text-[var(--c-muted)] mt-1">{testResult.error}</div>
                  </>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Install help */}
      {settings.ai_provider === "ollama" && (
        <Card className="p-6 bg-[color-mix(in_srgb,var(--c-surface)_40%,transparent)] border-[var(--c-border)] shadow-none">
          <h4 className="font-medium" style={{ fontFamily: "Work Sans" }}>How to install Ollama on {inst.os}</h4>
          <ol className="text-sm text-[var(--c-muted)] mt-3 space-y-2 list-decimal pl-5">
            <li>
              Install Ollama:
              <div className="mt-1 flex items-center gap-2">
                <code className="bg-[var(--c-ink)] text-[var(--c-bg)] px-2 py-1 rounded text-xs flex-1 truncate" title={inst.cmd}>{inst.cmd}</code>
                <Button size="sm" variant="ghost" onClick={() => copyCmd(inst.cmd)} data-testid="copy-install-cmd">
                  <Copy className="w-3.5 h-3.5" />
                </Button>
              </div>
              <a
                href="https://ollama.com/download"
                target="_blank"
                rel="noreferrer"
                className="text-xs text-[var(--c-primary)] underline mt-1 inline-flex items-center gap-1"
              >
                Open ollama.com/download <ExternalLink className="w-3 h-3" />
              </a>
            </li>
            <li>
              Start the Ollama server (most installers do this automatically; otherwise run <code className="bg-[var(--c-surface)] px-1.5 py-0.5 rounded">ollama serve</code>).
            </li>
            <li>
              Pull a model the first time:
              <div className="mt-1 flex items-center gap-2">
                <code className="bg-[var(--c-ink)] text-[var(--c-bg)] px-2 py-1 rounded text-xs flex-1">{pullCmd}</code>
                <Button size="sm" variant="ghost" onClick={() => copyCmd(pullCmd)} data-testid="copy-pull-cmd-2">
                  <Copy className="w-3.5 h-3.5" />
                </Button>
              </div>
              <p className="text-xs mt-1">Downloads ~3 GB once. Future runs are instant.</p>
            </li>
            <li>
              Click <strong>Test connection</strong> above. When it says "reachable", hit <strong>Save settings</strong>.
            </li>
          </ol>
        </Card>
      )}

      {/* Save */}
      <div className="flex items-center justify-end gap-3 sticky bottom-4 bg-[color-mix(in_srgb,var(--c-bg)_95%,transparent)] backdrop-blur-sm py-3 rounded-md">
        <Button
          onClick={save}
          disabled={saving}
          data-testid="save-settings-btn"
          className="bg-[var(--c-primary)] hover:bg-[var(--c-primary-deep)] text-[var(--c-on-primary)]"
        >
          {saving ? "Saving..." : "Save settings"}
        </Button>
      </div>
    </div>
  );
}
