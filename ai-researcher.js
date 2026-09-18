/**
 * ai-researcher.js
 * ----------------
 * Autonomous research and ideation engine for the LinkedIn Agent.
 *
 * Instead of repeating the same project or looping through a rigid scripted list:
 * 1. Analyzes all indexed repositories across the user's GitHub portfolio
 * 2. Checks recent posting history to prevent repeating the same repo or theme
 * 3. Uses an LLM to ideate an authentic, compelling technical angle
 * 4. Gathers relevant RAG context from MongoDB vector memory
 */

const { getDb, loadState, saveState, findRelevantMemories } = require("./mongo-store");
const { retrieveRelevantChunks } = require("./vector-store");
require("dotenv").config();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function callGeminiText(prompt) {
  const configuredModel = process.env.GEMINI_TEXT_MODEL;
  const candidateModels = Array.from(
    new Set([
      "gemini-3.5-flash-lite",
      "gemini-3.5-flash",
      "gemini-3.6-flash",
      "gemini-3.7-flash",
      configuredModel,
    ].filter(Boolean))
  );

  let lastError = null;
  for (const model of candidateModels) {
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": process.env.GEMINI_API_KEY,
          },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
          }),
        });

        if (!response.ok) {
          const errText = await response.text();
          lastError = new Error(`Gemini generateContent error (${response.status}): ${errText}`);
          if ((response.status === 503 || response.status === 429) && attempt < 2) {
            console.warn(`[AI Researcher] Model ${model} is busy (${response.status}), retrying in 1s...`);
            await sleep(1000);
            continue;
          }
          console.warn(`[AI Researcher] Model ${model} returned ${response.status}, switching to next candidate...`);
          break;
        }

        const data = await response.json();
        const textPart = data.candidates?.[0]?.content?.parts?.find((p) => p.text);
        const rawText = textPart ? textPart.text : data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!rawText) throw new Error("Empty response from Gemini");

        const jsonMatch = rawText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try {
            return JSON.parse(jsonMatch[0]);
          } catch {}
        }

        return {
          topic_title: "Key lessons building this project",
          technical_angle: rawText.slice(0, 150),
          search_query: "project",
        };
      } catch (err) {
        lastError = err;
        await sleep(1000);
      }
    }
  }
  throw lastError || new Error("All Gemini models failed in ai-researcher.");
}

/**
 * Get all known repositories from the portfolio catalog or memory collection
 */
async function getAllRepositories() {
  try {
    const db = await getDb();
    const catalog = await db.collection("portfolio_catalog").findOne({ _id: "github_portfolio" });
    if (catalog && catalog.repos && catalog.repos.length > 0) {
      // Filter out user's profile README repo (e.g. 'rexmarchen')
      return catalog.repos.filter((r) => r.name !== r.repoKey.split("/")[0]);
    }

    // Fallback: query memories collection directly
    const memories = await db
      .collection("memories")
      .find({ type: "github" })
      .project({ metadata: 1 })
      .toArray();

    const reposMap = new Map();
    for (const m of memories) {
      if (m.metadata?.repoName) {
        reposMap.set(m.metadata.repoName, {
          name: m.metadata.repoName,
          repoKey: m.metadata.repoKey,
          language: m.metadata.language || "Code",
          url: m.metadata.repoUrl || `https://github.com/${m.metadata.repoKey}`,
          description: "",
        });
      }
    }
    return Array.from(reposMap.values());
  } catch (err) {
    console.warn("[Repositories Warning] Could not fetch repositories from MongoDB:", err.message);
    return [];
  }
}

/**
 * Select an interesting repository to feature, avoiding recently posted ones
 */
async function pickRepositoryToResearch(explicitRepoName = null) {
  const allRepos = await getAllRepositories();
  if (!allRepos.length) {
    throw new Error("No repositories found in database. Run github-sync first.");
  }

  if (explicitRepoName) {
    const found = allRepos.find(
      (r) => r.name.toLowerCase() === explicitRepoName.toLowerCase()
    );
    if (found) return found;
  }

  const state = await loadState({ recentlyPostedRepos: [] });
  const recent = state.recentlyPostedRepos || [];

  // Filter repos that haven't been posted in the recent batch
  let candidates = allRepos.filter((r) => !recent.slice(0, 5).includes(r.name));

  // If all repos were posted recently, reset and use any repo not equal to the immediate last one
  if (candidates.length === 0) {
    const lastPosted = recent[0];
    candidates = allRepos.filter((r) => r.name !== lastPosted);
  }

  if (candidates.length === 0) {
    candidates = allRepos;
  }

  // Pick a candidate with high diversity (prefer projects with languages or descriptions)
  const sorted = candidates.sort(() => 0.5 - Math.random());
  return sorted[0];
}

/**
 * Autonomous Research Step:
 * 1. Takes the chosen repository
 * 2. Uses Gemini to brainstorm an authentic, engaging technical post angle
 * 3. Retrieves RAG chunks from MongoDB vector store for that angle
 */
async function researchTopicForPost(targetRepoName = null) {
  const repo = await pickRepositoryToResearch(targetRepoName);
  const db = await getDb();

  // Fetch the full stored memory for this repo to understand its README & details
  const repoMemory = await db.collection("memories").findOne({
    type: "github",
    "metadata.repoName": repo.name,
  });

  const repoContext = repoMemory?.content || `Project ${repo.name} in ${repo.language}`;

  const ideationPrompt = `You are the technical AI brain of Anshu Pal, a computer science student and software builder.
You need to choose a fresh, authentic engineering angle to write a LinkedIn post about one of your GitHub projects.

SELECTED REPOSITORY:
- Name: ${repo.name}
- Primary Tech/Language: ${repo.language || "Software Engineering"}
- Technical Context from Repo / README:
${repoContext.slice(0, 1500)}

Brainstorm a specific, compelling technical post topic about this project.
Choose an angle that sounds like a real developer sharing practical experience:
- Architectural or design decision (why this stack or pattern?)
- Overcoming a technical hurdle or bug
- Performance, state management, or UI challenge
- Key engineering lesson learned while building it

Do NOT create generic marketing topics like "Why AI is the future". Focus directly on the concrete project "${repo.name}".

Respond with ONLY valid JSON in this exact shape:
{
  "topic_title": "<short descriptive topic, e.g. 'Handling complex state in a TypeScript healthcare app'>",
  "technical_angle": "<1-2 sentences summarizing the core engineering insight or story>",
  "search_query": "<search keywords to retrieve supporting RAG context from the vector database>"
}`;

  console.log(`[AI Researcher] Brainstorming technical angle for project: ${repo.name}...`);
  const idea = await callGeminiText(ideationPrompt);

  // Retrieve RAG context using semantic search
  const searchQuery = idea.search_query || idea.topic_title || repo.name;
  console.log(`[AI Researcher] Retrieving RAG context for query: "${searchQuery}"...`);

  const ragParts = [];
  try {
    const memories = await findRelevantMemories(searchQuery, 4);
    for (const m of memories) {
      if (m.score > 0.4) {
        ragParts.push(`- [Memory (${m.type})]: ${m.content}`);
      }
    }
  } catch (ragErr) {
    console.warn("[AI Researcher] Memory retrieval warning:", ragErr.message);
  }

  // Also query local chunks if any exist
  try {
    const localChunks = await retrieveRelevantChunks(searchQuery, 3);
    for (const c of localChunks) {
      ragParts.push(`- [Document Chunk from ${c.source}]: ${c.text}`);
    }
  } catch {}

  // If semantic search was sparse, include the repo's own technical memory
  if (ragParts.length === 0 && repoMemory) {
    ragParts.push(`- [Repository Profile]: ${repoMemory.content}`);
  }

  return {
    repoName: repo.name,
    repoKey: repo.repoKey,
    repoUrl: repo.url || repo.repoUrl || `https://github.com/rexmarchen/${repo.name}`,
    language: repo.language,
    topicTitle: idea.topic_title,
    technicalAngle: idea.technical_angle,
    ragContext: ragParts.join("\n"),
  };
}

/**
 * Record that a repo was posted so we don't repeat it soon
 */
async function markRepoAsPosted(repoName) {
  try {
    const state = await loadState({ recentlyPostedRepos: [] });
    const recent = state.recentlyPostedRepos || [];
    const updated = [repoName, ...recent.filter((r) => r !== repoName)].slice(0, 8);
    await saveState({
      recentlyPostedRepos: updated,
      lastPostedRepo: repoName,
      lastPostedAt: new Date(),
    });
  } catch (err) {
    console.warn("[AI Researcher] Could not update recent repo state:", err.message);
  }
}

module.exports = {
  getAllRepositories,
  pickRepositoryToResearch,
  researchTopicForPost,
  markRepoAsPosted,
};
