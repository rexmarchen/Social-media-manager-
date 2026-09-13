/**
 * ingest.js
 * ---------
 * Scans the ./documents folder, and for every supported file:
 *   - Skips it if unchanged since the last run (tracked via content hash)
 *   - Re-embeds it if it's new or has changed
 *   - Removes its old vectors first if it changed, so stale chunks don't
 *     linger in the index
 *   - Removes vectors for any file that's been deleted from the folder
 *
 * This incremental approach means re-running ingest.js after adding one
 * new file only embeds that one file — not your entire document set —
 * which is what makes this efficient as your knowledge base grows.
 *
 * Run manually:  node ingest.js
 * Or let watch-ingest.js call this automatically on file changes.
 */

const fs = require("fs");
require("dotenv").config();
const path = require("path");
const crypto = require("crypto");

const { splitIntoChunks } = require("./chunker");
const { isSupported, extractText } = require("./file-readers");
const { addChunk, deleteChunk } = require("./vector-store");

const DOCUMENTS_DIR = path.join(__dirname, "documents");
const MANIFEST_PATH = path.join(__dirname, "ingest-manifest.json");

function loadManifest() {
  try {
    return JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));
  } catch {
    return {};
  }
}

function saveManifest(manifest) {
  fs.writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
}

function hashContent(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function walkDirectory(dir) {
  let results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results = results.concat(walkDirectory(fullPath));
    } else if (isSupported(fullPath)) {
      results.push(fullPath);
    }
  }
  return results;
}

async function ingestFile(filePath, manifest) {
  const relPath = path.relative(DOCUMENTS_DIR, filePath);
  const buffer = fs.readFileSync(filePath);
  const hash = hashContent(buffer);

  const existing = manifest[relPath];
  if (existing && existing.hash === hash) {
    console.log(`Unchanged, skipping: ${relPath}`);
    return;
  }

  // If this file was seen before but changed, delete its old chunks first
  if (existing) {
    console.log(`Changed, re-indexing: ${relPath}`);
    for (const chunkId of existing.chunkIds) {
      await deleteChunk(chunkId);
    }
  } else {
    console.log(`New file, indexing: ${relPath}`);
  }

  const text = await extractText(filePath);
  const chunks = splitIntoChunks(text);

  const chunkIds = [];
  for (let i = 0; i < chunks.length; i++) {
    const id = await addChunk(chunks[i], { source: relPath, chunkIndex: i });
    chunkIds.push(id);
  }

  manifest[relPath] = { hash, chunkIds, lastIndexed: new Date().toISOString() };
  console.log(`  -> ${chunks.length} chunk(s) embedded`);
}

async function removeDeletedFiles(currentFiles, manifest) {
  const currentRelPaths = new Set(
    currentFiles.map((f) => path.relative(DOCUMENTS_DIR, f))
  );

  for (const relPath of Object.keys(manifest)) {
    if (!currentRelPaths.has(relPath)) {
      console.log(`File removed, deleting its vectors: ${relPath}`);
      for (const chunkId of manifest[relPath].chunkIds) {
        await deleteChunk(chunkId);
      }
      delete manifest[relPath];
    }
  }
}

async function runIngest() {
  if (!process.env.GEMINI_API_KEY) {
    throw new Error("Missing GEMINI_API_KEY environment variable.");
  }

  if (!fs.existsSync(DOCUMENTS_DIR)) {
    fs.mkdirSync(DOCUMENTS_DIR, { recursive: true });
    console.log(`Created ${DOCUMENTS_DIR} — drop your files in there and run this again.`);
    return;
  }

  const manifest = loadManifest();
  const files = walkDirectory(DOCUMENTS_DIR);

  console.log(`Found ${files.length} supported file(s) in documents/`);

  for (const filePath of files) {
    try {
      await ingestFile(filePath, manifest);
    } catch (err) {
      console.error(`Failed to ingest ${filePath}: ${err.message}`);
    }
  }

  await removeDeletedFiles(files, manifest);
  saveManifest(manifest);

  console.log("Ingestion complete.");
}

// Allow running directly (`node ingest.js`) or importing runIngest() elsewhere
if (require.main === module) {
  runIngest().catch((err) => {
    console.error("Ingest failed:", err.message);
    process.exit(1);
  });
}

module.exports = { runIngest };
