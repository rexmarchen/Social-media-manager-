/**
 * daemon.js
 * ---------
 * 24/7 Watchdog Supervisor for the LinkedIn RAG Agent & Telegram Bot.
 * 
 * Responsibilities:
 * 1. Spawns and supervises `node server.js`.
 * 2. Pipes all logs to `bot-server.log` with timestamps.
 * 3. Auto-restarts server.js immediately if it ever crashes or gets terminated.
 * 4. Runs silently in the background with zero terminal interference.
 */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const LOG_FILE = path.join(__dirname, "bot-server.log");
const SERVER_SCRIPT = path.join(__dirname, "server.js");

function log(msg) {
  const line = `[${new Date().toISOString()}] [Supervisor] ${msg}\n`;
  console.log(line.trim());
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch {}
}

let child = null;
let isStopping = false;

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
  });

  child.on("error", (err) => {
    log(`Failed to spawn server.js: ${err.message}`);
  });

  child.on("exit", (code, signal) => {
    log(`server.js exited with code ${code}, signal: ${signal}`);
    child = null;

    if (!isStopping) {
      log("Restarting server.js in 3 seconds...");
      setTimeout(startServer, 3000);
    }
  });
}

process.on("SIGINT", () => {
  log("SIGINT received, shutting down supervisor...");
  isStopping = true;
  if (child) child.kill();
  process.exit(0);
});

process.on("SIGTERM", () => {
  log("SIGTERM received, shutting down supervisor...");
  isStopping = true;
  if (child) child.kill();
  process.exit(0);
});

startServer();
