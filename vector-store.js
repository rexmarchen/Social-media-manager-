/**
 * vector-store.js
 * ---------------
 * Wraps vectra's LocalIndex (a local, file-backed vector database — no
 * external service needed) and the Gemini embedding call, so both
 * ingest.js and agent-core.js can share the same logic.
 */

const path = require("path");
const { LocalIndex } = require("vectra");

const INDEX_PATH = path.join(__dirname, "vector-index");
const EMBEDDING_MODEL = "gemini-embedding-001"; // verify current name in Google AI Studio

let indexInstance = null;

async function getIndex() {
  if (indexInstance) return indexInstance;
  const index = new LocalIndex(INDEX_PATH);
  if (!(await index.isIndexCreated())) {
    await index.createIndex();
  }
  indexInstance = index;
  return index;
}

async function embedText(text) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${EMBEDDING_MODEL}:embedContent`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": process.env.GEMINI_API_KEY,
    },
    body: JSON.stringify({ content: { parts: [{ text }] } }),
  });
  if (!response.ok) {
    throw new Error(`Embedding error (${response.status}): ${await response.text()}`);
  }
  const data = await response.json();
  return data.embedding.values;
}

/**
 * Inserts one chunk into the vector index. Returns the inserted item's id,
 * which the caller should keep track of (e.g. in a manifest) so it can be
 * deleted later if the source file changes or is removed.
 */
async function addChunk(text, metadata) {
  const index = await getIndex();
  const vector = await embedText(text);
  const inserted = await index.insertItem({
    vector,
    metadata: { text, ...metadata },
  });
  return inserted.id;
}

async function deleteChunk(id) {
  const index = await getIndex();
  await index.deleteItem(id);
}

/**
 * Retrieves the topK most relevant chunks for a query string.
 * Returns an array of { text, score, ...metadata }.
 */
async function retrieveRelevantChunks(query, topK = 4) {
  const index = await getIndex();
  const queryVector = await embedText(query);
  const results = await index.queryItems(queryVector, topK);
  return results.map((r) => ({
    text: r.item.metadata.text,
    source: r.item.metadata.source,
    score: r.score,
  }));
}

module.exports = { getIndex, embedText, addChunk, deleteChunk, retrieveRelevantChunks };
