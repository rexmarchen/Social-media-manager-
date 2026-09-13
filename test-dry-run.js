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
    console.warn("⚠️  GEMINI_API_KEY is not set in environment or .env file.");
    console.log("Simulating output with mock retrieval...\n");

    const topic = "A recent project that didn't go as planned and what I learned";
    console.log(`[Dry Run] Simulated Topic: "${topic}"`);
    console.log("[Dry Run] Simulated Context:");
    console.log("- Placed in top 10 at a regional hackathon building a real-time collaboration tool.");
    console.log("- Shipped a caching layer that cut API latency by 40% for a course project.");
    console.log("\n[Dry Run] Simulated Post Output:");
    console.log(
      JSON.stringify(
        {
          post_text:
            "Last month, we tried to over-engineer a Redis caching layer before even benchmarking where our bottleneck was. Result? 40% latency drop on paper, but 3 days wasted fixing invalidation bugs.\n\nPremature optimization really is the root of all evil in course projects.\n\nCS folks: what is the most unnecessary optimization you spent hours building?",
          needs_image: false,
          image_prompt: "",
        },
        null,
        2
      )
    );
    console.log("\n💡 Add your GEMINI_API_KEY to .env to run real generation!");
    return;
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
