// Electron main process for Ledgerly desktop
// Spawns the FastAPI backend on localhost:8001 and loads the built React frontend.
const { app, BrowserWindow, Menu, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");

let mainWindow;
let backendProcess;

const isDev = !app.isPackaged;
const BACKEND_PORT = 8001;

function resolvePython() {
  // Allow user override
  if (process.env.LEDGERLY_PYTHON) return process.env.LEDGERLY_PYTHON;
  return process.platform === "win32" ? "python" : "python3";
}

function resolveBackendDir() {
  if (isDev) {
    return path.join(__dirname, "..", "backend");
  }
  // packaged: extraResources places backend under resources/backend
  return path.join(process.resourcesPath, "backend");
}

function startBackend() {
  const backendDir = resolveBackendDir();
  if (!fs.existsSync(path.join(backendDir, "server.py"))) {
    console.error("[ledgerly] backend not found at", backendDir);
    return;
  }

  // Persist SQLite db in user data dir so installs don't clobber each other.
  const userData = app.getPath("userData");
  const sqlitePath = path.join(userData, "ledgerly.db");

  const python = resolvePython();
  console.log("[ledgerly] starting backend:", python, "in", backendDir);
  console.log("[ledgerly] sqlite db at:", sqlitePath);

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
      },
    }
  );

  backendProcess.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backendProcess.stderr.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  backendProcess.on("exit", (code) => {
    console.log("[ledgerly] backend exited:", code);
  });
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    try { backendProcess.kill(); } catch (e) { /* noop */ }
    backendProcess = null;
  }
}

function waitForBackend(retries = 30) {
  return new Promise((resolve) => {
    const http = require("http");
    let tries = 0;
    const tick = () => {
      tries++;
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/`, (res) => {
        if (res.statusCode === 200) resolve(true);
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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#FDFBF7",
    title: "Ledgerly",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const indexPath = isDev
    ? `http://127.0.0.1:3000` // dev mode: run frontend with `yarn start` in /app/frontend
    : `file://${path.join(__dirname, "..", "frontend", "build", "index.html")}`;

  mainWindow.loadURL(indexPath);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(async () => {
  startBackend();
  await waitForBackend();
  createWindow();

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
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => stopBackend());
