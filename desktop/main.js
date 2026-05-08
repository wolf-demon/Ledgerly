// Electron main process for Ledgerly desktop
// Spawns the FastAPI backend on localhost:8001 and loads the built React frontend.
const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");

let mainWindow;
let backendProcess;

const isDev = !app.isPackaged;
const BACKEND_PORT = 8001;
const DEBUG = !!process.env.LEDGERLY_DEBUG || isDev;

function logFile() {
  return path.join(app.getPath("userData"), "ledgerly.log");
}
function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.map(String).join(" ")}\n`;
  process.stdout.write(line);
  try { fs.appendFileSync(logFile(), line); } catch (e) { /* ignore */ }
}

function resolvePython() {
  // 1. Explicit override
  if (process.env.LEDGERLY_PYTHON && fs.existsSync(process.env.LEDGERLY_PYTHON)) {
    return process.env.LEDGERLY_PYTHON;
  }
  // 2. Bundled python-build-standalone shipped via extraResources
  const bundledRoot = isDev
    ? path.join(__dirname, "python-runtime")
    : path.join(process.resourcesPath, "python");
  const candidates =
    process.platform === "win32"
      ? [path.join(bundledRoot, "python.exe")]
      : [path.join(bundledRoot, "bin", "python3"), path.join(bundledRoot, "bin", "python")];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  // 3. Fallback to system python
  return process.platform === "win32" ? "python" : "python3";
}

function resolveBackendDir() {
  if (isDev) return path.join(__dirname, "..", "backend");
  return path.join(process.resourcesPath, "backend");
}

function resolveFrontendIndex() {
  if (isDev) return null; // dev uses http://127.0.0.1:3000
  return path.join(process.resourcesPath, "frontend", "index.html");
}

function startBackend() {
  const backendDir = resolveBackendDir();
  if (!fs.existsSync(path.join(backendDir, "server.py"))) {
    log("FATAL: backend not found at", backendDir);
    return false;
  }

  const userData = app.getPath("userData");
  try { fs.mkdirSync(userData, { recursive: true }); } catch (e) { /* ignore */ }
  const sqlitePath = path.join(userData, "ledgerly.db");
  const python = resolvePython();
  log("starting backend:", python, "in", backendDir);
  log("sqlite db at:", sqlitePath);

  try {
    backendProcess = spawn(
      python,
      ["-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
      {
        cwd: backendDir,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          STORAGE: "sqlite",
          SQLITE_PATH: sqlitePath,
          CORS_ORIGINS: "*",
        },
      }
    );
  } catch (e) {
    log("FATAL: failed to spawn python:", e.message);
    return false;
  }

  backendProcess.stdout.on("data", (d) => log("[backend]", d.toString().trim()));
  backendProcess.stderr.on("data", (d) => log("[backend!]", d.toString().trim()));
  backendProcess.on("error", (e) => log("[backend error]", e.message));
  backendProcess.on("exit", (code) => log("backend exited:", code));
  return true;
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    try { backendProcess.kill(); } catch (e) { /* noop */ }
    backendProcess = null;
  }
}

function waitForBackend(retries = 60) {
  return new Promise((resolve) => {
    let tries = 0;
    const tick = () => {
      tries++;
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/`, (res) => {
        if (res.statusCode === 200) { log("backend ready after", tries, "tries"); resolve(true); }
        else if (tries >= retries) resolve(false);
        else setTimeout(tick, 500);
      });
      req.on("error", () => {
        if (tries >= retries) resolve(false);
        else setTimeout(tick, 500);
      });
    };
    tick();
  });
}

function showFatal(title, body) {
  dialog.showMessageBoxSync({
    type: "error",
    title: "Ledgerly — startup error",
    message: title,
    detail: body + "\n\nLog file: " + logFile(),
    buttons: ["Open log", "Quit"],
  }) === 0 && shell.openPath(logFile());
}

function createWindow(loadTarget) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#FDFBF7",
    title: "Ledgerly",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: !isDev,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());

  mainWindow.webContents.on("did-fail-load", (_, code, desc, url) => {
    log("did-fail-load:", code, desc, url);
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (DEBUG) mainWindow.webContents.openDevTools({ mode: "detach" });

  if (loadTarget.startsWith("http")) {
    mainWindow.loadURL(loadTarget);
  } else {
    mainWindow.loadFile(loadTarget);
  }
}

app.whenReady().then(async () => {
  log("Ledgerly starting | packaged=", app.isPackaged, "platform=", process.platform);
  log("resourcesPath=", process.resourcesPath);

  const ok = startBackend();
  if (!ok) {
    showFatal(
      "Could not start the local backend.",
      "The bundled Python runtime appears to be missing or corrupted.\nPlease re-install Ledgerly. If the problem persists, set LEDGERLY_PYTHON to a working python3 executable.\nSee log for details."
    );
  } else {
    const ready = await waitForBackend();
    if (!ready) log("WARNING: backend did not respond within timeout — UI will load anyway");
  }

  let loadTarget;
  if (isDev) {
    loadTarget = "http://127.0.0.1:3000";
  } else {
    const indexPath = resolveFrontendIndex();
    if (!fs.existsSync(indexPath)) {
      showFatal(
        "Frontend bundle not found.",
        `Expected at: ${indexPath}\n\nThe app was packaged incorrectly — please re-run desktop\\build.ps1 or build.sh.`
      );
      app.quit();
      return;
    }
    loadTarget = indexPath;
  }
  log("loading window:", loadTarget);
  createWindow(loadTarget);

  if (process.platform === "darwin") {
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { role: "appMenu" },
      { role: "editMenu" },
      { role: "viewMenu" },
      { role: "windowMenu" },
    ]));
  } else {
    Menu.setApplicationMenu(null);
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(loadTarget);
  });
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => stopBackend());
