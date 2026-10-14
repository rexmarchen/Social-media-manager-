/**
 * Safe Dry-Run Script
 * -------------------
 * Tests knowledge base retrieval and Gemini post generation WITHOUT publishing
 * to LinkedIn and WITHOUT requiring LinkedIn access tokens.
 *
 * Usage:
 *   node test-dry-run.js
 */

try {
  require("dotenv").config();
} catch (e) {}

const { getNextTopic, retrieveContext, generatePost, CONFIG } = require("./agent");

async function dryRun() {
  console.log("==========================================");
  console.log("       LinkedIn RAG Agent - Dry Run       ");
  console.log("==========================================");
  console.log(`Active Models:`);
  console.log(`  - Text Model:      ${CONFIG.textModel}`);
  console.log(`  - Embedding Model: ${CONFIG.embeddingModel}`);
  console.log(`  - Image Model:     ${CONFIG.imageModel}`);
  console.log("==========================================\n");

  if (!process.env.GEMINI_API_KEY) {
    throw new Error("GEMINI_API_KEY is not set in environment or .env file.");
  }

  const topic = getNextTopic();
  console.log(`[Dry Run] Selected Topic: "${topic}"\n`);

  console.log("[Dry Run] Retrieving relevant context via RAG embeddings...");
  const context = await retrieveContext(topic);
  console.log(`[Dry Run] Retrieved Context Chunks:\n${context || "(None)"}\n`);

  console.log("[Dry Run] Requesting post draft from Gemini...");
  const result = await generatePost(topic, context);

  console.log("\n---------------- Generated Post ----------------");
  console.log(result.post_text);
  console.log("------------------------------------------------\n");
  console.log(`Needs Image: ${result.needs_image}`);
  if (result.needs_image) {
    console.log(`Image Prompt: "${result.image_prompt}"`);
  }
  console.log("\n✅ Dry run completed successfully! (No LinkedIn APIs called)");
}

dryRun().catch((err) => {
  console.error("\n❌ Dry run encountered an error:", err.message);
  process.exit(1);
});
