/**
 * mongo-store.js
 * --------------
 * Persistent cloud memory and state storage on MongoDB Atlas.
 * Stores learnings, project achievements, and GitHub activity embeddings
 * so the LinkedIn agent has permanent RAG context across 24/7 Render restarts.
 */

const { MongoClient } = require("mongodb");
require("dotenv").config();

const EMBEDDING_MODEL = process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001";
let client = null;
let dbInstance = null;

async function getDb() {
  if (dbInstance) return dbInstance;
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    throw new Error("Missing MONGODB_URI environment variable.");
  }
  client = new MongoClient(uri, {
    maxPoolSize: 10,
    serverSelectionTimeoutMS: 8000,
  });
  await client.connect();
  dbInstance = client.db("linkedin_agent");
  return dbInstance;
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

function cosineSimilarity(vecA, vecB) {
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < vecA.length; i++) {
    dotProduct += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  const denominator = Math.sqrt(normA) * Math.sqrt(normB);
  return denominator === 0 ? 0 : dotProduct / denominator;
}

/**
 * Save a new memory (learning, project, research, or GitHub activity)
 */
async function addMemory(content, type = "learning", source = "telegram", metadata = {}) {
  const db = await getDb();
  const embedding = await embedText(content);

  const doc = {
    content,
    type,
    source,
    metadata,
    embedding,
    createdAt: new Date(),
  };

  const result = await db.collection("memories").insertOne(doc);
  return result.insertedId;
}

/**
 * Retrieve recent memories
 */
async function getRecentMemories(limit = 5, type = null) {
  const db = await getDb();
  const filter = type ? { type } : {};
  return db
    .collection("memories")
    .find(filter)
    .sort({ createdAt: -1 })
    .limit(limit)
    .project({ embedding: 0 })
    .toArray();
}

/**
 * Perform semantic similarity search over stored memories using cosine similarity
 */
async function findRelevantMemories(queryText, topK = 4) {
  const db = await getDb();
  const queryVector = await embedText(queryText);

  // Fetch candidate memories with embeddings
  const memories = await db
    .collection("memories")
    .find({})
    .sort({ createdAt: -1 })
    .limit(100)
    .toArray();

  if (!memories.length) return [];

  const scored = memories.map((m) => ({
    id: m._id,
    content: m.content,
    type: m.type,
    source: m.source,
    createdAt: m.createdAt,
    score: cosineSimilarity(queryVector, m.embedding),
  }));

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, topK);
}

/**
 * Persistent state in MongoDB (replaces local state.json)
 */
async function loadState(fallback = { lastIndex: -1, scheduleEnabled: true }) {
  try {
    const db = await getDb();
    const doc = await db.collection("state").findOne({ _id: "bot_state" });
    if (doc) {
      return {
        ...fallback,
        ...doc,
        lastIndex: doc.lastIndex ?? fallback.lastIndex,
        scheduleEnabled: doc.scheduleEnabled ?? fallback.scheduleEnabled,
      };
    }
  } catch (err) {
    console.warn("Could not read state from MongoDB:", err.message);
  }
  return fallback;
}

async function saveState(updates) {
  try {
    const db = await getDb();
    await db.collection("state").updateOne(
      { _id: "bot_state" },
      { $set: { ...updates, updatedAt: new Date() } },
      { upsert: true }
    );
  } catch (err) {
    console.warn("Could not save state to MongoDB:", err.message);
  }
}

module.exports = {
  getDb,
  embedText,
  addMemory,
  getRecentMemories,
  findRelevantMemories,
  loadState,
  saveState,
};
