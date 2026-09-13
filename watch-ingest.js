/**
 * watch-ingest.js
 * ---------------
 * Watches the ./documents folder and automatically re-runs ingestion
 * whenever a file is added, changed, or removed — this is what makes
 * "reads from my laptop automatically" actually true in real time.
 *
 * Run this alongside server.js (in a second terminal, or via a process
 * manager like pm2) while you're actively adding documents.
 *
 * Usage: node watch-ingest.js
 */

const chokidar = require("chokidar");
const path = require("path");
const { runIngest } = require("./ingest");

const DOCUMENTS_DIR = path.join(__dirname, "documents");

let debounceTimer = null;
const DEBOUNCE_MS = 2000; // wait 2s after the last change before re-ingesting,
                           // so saving a big file doesn't trigger multiple runs

function scheduleIngest(reason) {
  console.log(`Change detected (${reason}) — re-ingesting in ${DEBOUNCE_MS / 1000}s...`);
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    try {
      await runIngest();
    } catch (err) {
      console.error("Auto re-ingest failed:", err.message);
    }
  }, DEBOUNCE_MS);
}

console.log(`Watching ${DOCUMENTS_DIR} for changes...`);

const watcher = chokidar.watch(DOCUMENTS_DIR, {
  ignoreInitial: true, // don't trigger for files that already existed at startup
});

watcher
  .on("add", (filePath) => scheduleIngest(`added: ${filePath}`))
  .on("change", (filePath) => scheduleIngest(`changed: ${filePath}`))
  .on("unlink", (filePath) => scheduleIngest(`removed: ${filePath}`));
