// updater.js — Wraps electron-updater with logs, user dialogs, and manual-check support.
//
// How publishing works:
//   `electron-builder` pushes the built artifacts plus a `latest.yml` (Win/Linux) or
//   `latest-mac.yml` to whatever target is configured in package.json -> build.publish.
//   On startup, the installed app fetches that yml from the same target and decides
//   whether to download a newer version. End-users get a prompt; updates apply on quit.
//
// Default provider is GitHub Releases of `LEDGERLY_UPDATE_REPO` (set at build time).
// Override at runtime by setting `LEDGERLY_UPDATE_FEED=https://your-cdn/path/`.
const { app, dialog, Menu } = require("electron");
const { autoUpdater } = require("electron-updater");

const SIX_HOURS_MS = 6 * 60 * 60 * 1000;
const PRERELEASE_CHANNELS = new Set(["alpha", "beta", "next"]);

let log = console; // replaced by setLogger() below

function setLogger(externalLog) {
  log = externalLog || console;
}

function configureUpdater() {
  // Forward updater logs into our log file.
  autoUpdater.logger = {
    info: (m) => log.log("[updater]", m),
    warn: (m) => log.log("[updater!]", m),
    error: (m) => log.log("[updater!!]", m),
    debug: (m) => log.log("[updater.dbg]", m),
  };
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  // Allow swapping to a custom feed URL via env (handy for staging channels).
  const feed = process.env.LEDGERLY_UPDATE_FEED;
  if (feed) {
    autoUpdater.setFeedURL({ provider: "generic", url: feed });
    log.log("[updater] using generic feed:", feed);
  }

  // Pre-release support: opt-in via env or by installing a pre-release version.
  const channel = (process.env.LEDGERLY_UPDATE_CHANNEL || "").toLowerCase();
  if (channel) {
    autoUpdater.channel = channel;
    autoUpdater.allowPrerelease = PRERELEASE_CHANNELS.has(channel);
  }
}

function wireEvents(getWindow) {
  let updateInfo = null;

  autoUpdater.on("checking-for-update", () => log.log("[updater] checking..."));
  autoUpdater.on("update-not-available", (info) => log.log("[updater] up-to-date", info && info.version));
  autoUpdater.on("error", (err) => log.log("[updater] error:", err && err.message));

  autoUpdater.on("update-available", (info) => {
    updateInfo = info;
    log.log("[updater] update available:", info.version);
    const win = getWindow();
    if (!win) return;
    dialog.showMessageBox(win, {
      type: "info",
      title: "Ledgerly update available",
      message: `Ledgerly ${info.version} is available.`,
      detail: "Downloading in the background. We'll let you know when it's ready to install.",
      buttons: ["OK"],
      defaultId: 0,
    });
  });

  autoUpdater.on("download-progress", (p) => {
    log.log(`[updater] downloading ${Math.round(p.percent)}% @ ${Math.round(p.bytesPerSecond / 1024)} KB/s`);
  });

  autoUpdater.on("update-downloaded", (info) => {
    log.log("[updater] downloaded:", info.version);
    const win = getWindow();
    const choice = dialog.showMessageBoxSync(win || undefined, {
      type: "question",
      title: "Ledgerly update ready",
      message: `Ledgerly ${info.version} is ready to install.`,
      detail: "Restart now to apply, or it will be applied automatically next time you quit.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    });
    if (choice === 0) {
      // Allow the app a tick to clean up backend before relaunch.
      setImmediate(() => autoUpdater.quitAndInstall());
    }
  });

  return {
    getUpdateInfo: () => updateInfo,
  };
}

async function checkOnStartup() {
  if (!app.isPackaged) {
    log.log("[updater] dev mode — skipping update check");
    return;
  }
  try {
    await autoUpdater.checkForUpdates();
  } catch (e) {
    log.log("[updater] check failed:", e && e.message);
  }
}

function schedulePeriodicChecks() {
  if (!app.isPackaged) return;
  setInterval(() => {
    autoUpdater.checkForUpdates().catch((e) => log.log("[updater] periodic check failed:", e && e.message));
  }, SIX_HOURS_MS);
}

function buildHelpMenuItem(getWindow) {
  return {
    label: "Check for Updates…",
    click: async () => {
      if (!app.isPackaged) {
        dialog.showMessageBox(getWindow() || undefined, {
          type: "info",
          title: "Ledgerly",
          message: "Updates are only checked in the packaged app.",
        });
        return;
      }
      try {
        const result = await autoUpdater.checkForUpdates();
        if (!result || !result.updateInfo || result.updateInfo.version === app.getVersion()) {
          dialog.showMessageBox(getWindow() || undefined, {
            type: "info",
            title: "Ledgerly",
            message: `You're up to date — running ${app.getVersion()}.`,
          });
        }
      } catch (e) {
        dialog.showMessageBox(getWindow() || undefined, {
          type: "error",
          title: "Ledgerly update check failed",
          message: e && e.message ? e.message : String(e),
        });
      }
    },
  };
}

function init({ getWindow, logger }) {
  setLogger(logger);
  configureUpdater();
  const handle = wireEvents(getWindow);
  // Wait a few seconds so the backend + UI finish booting before we hit the network.
  setTimeout(() => { checkOnStartup(); }, 4000);
  schedulePeriodicChecks();
  return {
    ...handle,
    helpMenuItem: () => buildHelpMenuItem(getWindow),
    checkNow: () => autoUpdater.checkForUpdates(),
  };
}

module.exports = { init };
