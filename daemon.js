/**
 * daemon.js
 * ---------
 * 24/7 Watchdog Supervisor for the LinkedIn RAG Agent & Telegram Bot.
 * 
 * Production Features:
 * 1. Spawns and supervises `node server.js`.
 * 2. Active HTTP Health Checker: Probes http://localhost:3000/health every 30 seconds.
 * 3. Auto-restarts server.js immediately if it ever crashes, hangs, or stops responding.
 * 4. Pipes all logs to `bot-server.log` with timestamps.
 * 5. Emits periodic 24/7 heartbeat status so you know it never sleeps.
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const LOG_FILE = path.join(__dirname, "bot-server.log");
const SERVER_SCRIPT = path.join(__dirname, "server.js");
const PORT = process.env.PORT || 3000;
const HEALTH_URL = `http://localhost:${PORT}/health`;

function log(msg) {
  const line = `[${new Date().toISOString()}] [Supervisor] ${msg}\n`;
  console.log(line.trim());
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch {}
}

let child = null;
let isStopping = false;
let failedHealthChecks = 0;
let healthCheckTimer = null;
let heartbeatTimer = null;

async function checkHealth() {
  if (!child || isStopping) return;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(HEALTH_URL, { signal: controller.signal });
    clearTimeout(timeout);

    if (res.ok) {
      failedHealthChecks = 0;
    } else {
      failedHealthChecks++;
      log(`Health check returned HTTP ${res.status} (${failedHealthChecks}/3 warnings)`);
    }
  } catch (err) {
    failedHealthChecks++;
    log(`Health check failed: ${err.message} (${failedHealthChecks}/3 warnings)`);
  }

  if (failedHealthChecks >= 3) {
    log("Server appears unresponsive after 3 failed health probes. Auto-recovering server.js now...");
    failedHealthChecks = 0;
    if (child) {
      try {
        child.kill();
      } catch {}
    }
  }
}

function startServer() {
  if (isStopping) return;

  log("Starting LinkedIn agent server (server.js)...");

  const logStream = fs.createWriteStream(LOG_FILE, { flags: "a" });

  child = spawn("node", [SERVER_SCRIPT], {
    cwd: __dirname,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.pipe(logStream);
  child.stderr.pipe(logStream);

  child.on("spawn", () => {
    log(`server.js spawned successfully with PID: ${child.pid}`);
    failedHealthChecks = 0;
  });

  child.on("error", (err) => {
    log(`Failed to spawn server.js: ${err.message}`);
  });

  child.on("exit", (code, signal) => {
    log(`server.js exited with code ${code}, signal: ${signal}`);
    child = null;

    if (!isStopping) {
      log("Restarting server.js in 3 seconds (24/7 self-healing watchdog active)...");
      setTimeout(startServer, 3000);
    }
  });
}

// Start active health probe loop (every 30 seconds)
healthCheckTimer = setInterval(checkHealth, 30000);

// Periodic 24/7 Heartbeat (every 15 minutes)
heartbeatTimer = setInterval(() => {
  if (child && !isStopping) {
    log(`24/7 Heartbeat: Agent server is online and active (PID: ${child.pid}). Cron and Telegram active.`);
  }
}, 15 * 60 * 1000);

function shutdown() {
  log("Shutdown signal received, stopping supervisor...");
  isStopping = true;
  if (healthCheckTimer) clearInterval(healthCheckTimer);
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (child) child.kill();
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

startServer();
