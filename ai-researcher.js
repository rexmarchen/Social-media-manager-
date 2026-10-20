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

const { callGeminiResilient } = require("./gemini-resilience");

async function callGeminiText(prompt) {
  const result = await callGeminiResilient({
    prompt,
    expectJson: true,
    temperature: 0.7,
    timeoutMs: 25000,
  });

  const parsed = result.data;
  if (parsed && parsed.topic_title && parsed.technical_angle) {
    return {
      topic_title: String(parsed.topic_title).trim(),
      technical_angle: String(parsed.technical_angle).trim(),
      search_query: String(parsed.search_query || parsed.topic_title).trim(),
    };
  }

  throw new Error("Invalid schema received in ideation response.");
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
/**
 * Autonomous Research for Cutting-Edge Tech & Architecture Topics:
 * Explores software engineering, database internals, AI systems, and concurrency.
 */
async function researchTechTopic(options = {}) {
  const isOwner = Boolean(options.isOwner || (!options.authorName && (options.userId == 1 || options.userId === '1')));
  const authorName = options.authorName || (isOwner ? "Anshu Pal" : "Software Engineer");
  const fs = require("fs");
  const path = require("path");

  let topicsList = [];
  try {
    const topicsPath = path.join(__dirname, "topics.json");
    if (fs.existsSync(topicsPath)) {
      topicsList = JSON.parse(fs.readFileSync(topicsPath, "utf8"));
    }
  } catch {}

  let notesContext = "";
  try {
    const notesPath = path.join(__dirname, "knowledge_base", "notes.md");
    if (fs.existsSync(notesPath)) {
      notesContext = fs.readFileSync(notesPath, "utf8");
    }
  } catch {}

  const state = await loadState({ recentTechTopics: [] });
  const recentTopics = state.recentTechTopics || [];

  const personaPrompt = isOwner
    ? "You are the technical AI brain of Anshu Pal, a software systems engineer and builder."
    : `You are the technical AI brain of ${authorName}, an experienced Senior Software Engineer and systems architect.\nCRITICAL IDENTITY RULE: This is ${authorName}'s personal LinkedIn account. NEVER mention Anshu Pal, CGC University, or unrelated student projects (like library or student management systems).`;

  const techPrompt = `${personaPrompt}
Generate an authentic, cutting-edge technical post topic focused on deep software engineering, system design, or distributed systems architecture.

SEED TOPICS & INSPIRATION:
${topicsList.map((t) => `- ${t}`).join("\n")}

AUTHOR'S ENGINEERING BACKGROUND & NOTES:
${notesContext}

RECENTLY COVERED TOPICS (AVOID REPEATING THESE):
${recentTopics.slice(0, 5).map((t) => `- ${t}`).join("\n")}

CORE THEMES TO EXPLORE:
- Database internals & query latency (e.g. MongoDB compound indexes, execution plans, B-trees)
- Systems design & caching (e.g. Redis caching layers, measuring p95/p99 latency)
- Asynchronous concurrency & runtime edge cases (e.g. Node.js event loop, race conditions)
- Modern AI & LLM engineering (e.g. deterministic RAG pipelines, type-safe schema validation)
- Real-world DSA in production code (e.g. hash maps, two-pointer search optimization)
- Security & auth architecture (e.g. JWT vs secure HTTP-only cookies, token rotation)

Choose a fresh, authentic engineering angle that sounds like a developer sharing hard-earned technical wisdom.
Respond with ONLY valid JSON in this exact shape:
{
  "topic_title": "<concise title, e.g. 'MongoDB compound indexes vs single-field indexes in high-throughput query pipelines'>",
  "technical_angle": "<1-2 sentences summarizing the core technical insight, benchmark, or trade-off>",
  "search_query": "<keywords to query vector database for supporting context>"
}`;

  console.log("[AI Researcher] Synthesizing cutting-edge tech research angle...");
  const idea = await callGeminiText(techPrompt);

  const searchQuery = idea.search_query || idea.topic_title;
  const ragParts = [];

  try {
    const memories = await findRelevantMemories(searchQuery, 4);
    for (const m of memories) {
      if (m.score > 0.35) {
        ragParts.push(`- [Memory (${m.type})]: ${m.content}`);
      }
    }
  } catch (ragErr) {
    console.warn("[AI Researcher] Memory retrieval notice:", ragErr.message);
  }

  try {
    const localChunks = await retrieveRelevantChunks(searchQuery, 3);
    for (const c of localChunks) {
      ragParts.push(`- [Document Chunk from ${c.source}]: ${c.text}`);
    }
  } catch {}

  if (ragParts.length === 0 && notesContext) {
    ragParts.push(`- [Author Engineering Context]: ${notesContext}`);
  }

  return {
    category: "tech_research",
    repoName: "System Architecture & CS",
    repoKey: "rexmarchen/engineering-research",
    repoUrl: "https://github.com/rexmarchen",
    language: "Systems & Architecture",
    topicTitle: idea.topic_title,
    technicalAngle: idea.technical_angle,
    ragContext: ragParts.join("\n"),
  };
}

/**
 * Autonomous Research Step:
 * Intelligently balances between:
 * 1. Project Architecture Deep-Dives (hands-on code from user's GitHub repos)
 * 2. Cutting-Edge Tech Research (system design, databases, AI pipelines, concurrency)
 */
async function researchTopicForPost(targetParam = null, options = {}) {
  const isOwner = Boolean(options.isOwner || (!options.authorName && (options.userId == 1 || options.userId === '1')));

  // 1. If explicit user topic provided, use it directly
  if (options.topic && options.topic.trim()) {
    return {
      category: "tech_research",
      repoName: "System Architecture",
      repoKey: "architecture/engineering",
      repoUrl: "",
      language: "System Design",
      topicTitle: options.topic.trim(),
      technicalAngle: options.topic.trim(),
      ragContext: "",
    };
  }

  // 2. If NOT owner (e.g. any new user like Apurav Sharma), NEVER feature owner's personal student repos!
  // Always provide authentic industry-grade technical engineering topics!
  if (!isOwner) {
    return await researchTechTopic(options);
  }
  const isExplicitTech = targetParam && ["tech", "research", "architecture", "cs"].includes(targetParam.toLowerCase());

  if (isExplicitTech) {
    return await researchTechTopic(options);
  }

  if (targetParam) {
    // Explicit project requested
    return await researchProjectTopic(targetParam);
  }

  // Autonomous mode: check last category to alternate between projects and tech research
  const state = await loadState({ lastPostCategory: "project" });
  const lastCategory = state.lastPostCategory || "project";

  if (lastCategory === "project") {
    console.log("[AI Researcher] Smart rotation active: Previous post was a Project. Selected mode: CUTTING-EDGE TECH RESEARCH.");
    return await researchTechTopic();
  } else {
    console.log("[AI Researcher] Smart rotation active: Previous post was Tech Research. Selected mode: PROJECT ARCHITECTURE DEEP-DIVE.");
    return await researchProjectTopic();
  }
}

async function researchProjectTopic(targetRepoName = null) {
  const repo = await pickRepositoryToResearch(targetRepoName);
  const db = await getDb();

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

  try {
    const localChunks = await retrieveRelevantChunks(searchQuery, 3);
    for (const c of localChunks) {
      ragParts.push(`- [Document Chunk from ${c.source}]: ${c.text}`);
    }
  } catch {}

  if (ragParts.length === 0 && repoMemory) {
    ragParts.push(`- [Repository Profile]: ${repoMemory.content}`);
  }

  return {
    category: "project",
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
  researchTechTopic,
  researchProjectTopic,
  markRepoAsPosted,
};
