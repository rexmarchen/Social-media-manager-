/**
 * test-autonomous-research.js
 * ----------------------------
 * Safely tests the Autonomous AI Research & RAG generation pipeline.
 * Does NOT post to LinkedIn.
 */

require("dotenv").config();
const { researchTopicForPost, getAllRepositories } = require("./ai-researcher");
const { generatePost } = require("./agent-core");

async function main() {
  console.log("==================================================");
  console.log("   Testing Autonomous AI Multi-Repo RAG Pipeline  ");
  console.log("==================================================\n");

  console.log("1. Fetching all available repositories in portfolio...");
  const repos = await getAllRepositories();
  console.log(`Found ${repos.length} repositories:`);
  repos.forEach((r, idx) => console.log(`   ${idx + 1}. ${r.name} (${r.language})`));
  console.log("");

  console.log("2. Running Autonomous AI Researcher (selecting project & ideating angle)...");
  const research = await researchTopicForPost();
  console.log("\n[AI Researcher Selected Project]");
  console.log(`- Project Name:    ${research.repoName}`);
  console.log(`- Tech/Language:   ${research.language}`);
  console.log(`- Repository URL:  ${research.repoUrl}`);
  console.log(`- Topic Title:     ${research.topicTitle}`);
  console.log(`- Technical Angle: ${research.technicalAngle}`);
  console.log("\n[Retrieved RAG Context (from Vector DB & Repo)]: ");
  console.log(research.ragContext || "(No context retrieved)");
  console.log("\n--------------------------------------------------");

  console.log("3. Generating LinkedIn post via Gemini with authentic voice...");
  const postResult = await generatePost(
    `${research.topicTitle} (${research.repoName})`,
    research.ragContext
  );

  console.log("\n[Generated LinkedIn Post Draft]:");
  console.log(postResult.post_text);
  console.log("\n[Image Decision by AI]:");
  console.log(`- Needs Image: ${postResult.needs_image}`);
  if (postResult.needs_image) {
    console.log(`- Dynamic Image Prompt: "${postResult.image_prompt}"`);
  } else {
    console.log(`- Clean text post (no unwanted photo attached).`);
  }
  console.log("\n==================================================");
  console.log("   Test Completed Successfully!                   ");
  console.log("==================================================");
  process.exit(0);
}

main().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
