/**
 * github-sync.js
 * --------------
 * Deeply syncs ALL public GitHub repositories for the user, extracting:
 *   - Repository metadata & topics
 *   - README content (architecture, features, tech stack)
 *   - Key file structure
 *   - Recent commit activity
 * Stores rich embeddings in MongoDB Atlas vector memory (RAG)
 * and maintains a portfolio inventory for the autonomous AI researcher.
 */

const { getDb, addMemory } = require("./mongo-store");
require("dotenv").config();

const GITHUB_USERNAME = process.env.GITHUB_USERNAME || "rexmarchen";

async function fetchJSON(url, customHeaders = {}) {
  const headers = {
    "User-Agent": "linkedin-automation-agent",
    Accept: "application/vnd.github.v3+json",
    ...customHeaders,
  };
  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `token ${process.env.GITHUB_TOKEN}`;
  }
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`GitHub API error (${res.status}): ${await res.text()}`);
  }
  return res.json();
}

async function fetchRaw(url) {
  const headers = {
    "User-Agent": "linkedin-automation-agent",
    Accept: "application/vnd.github.v3.raw",
  };
  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `token ${process.env.GITHUB_TOKEN}`;
  }
  const res = await fetch(url, { headers });
  if (!res.ok) return null;
  return res.text();
}

/**
 * Clean markdown content to extract meaningful text without heavy markdown markup
 */
function cleanMarkdown(mdText) {
  if (!mdText) return "";
  return mdText
    .replace(/<[^>]*>/g, "") // remove html tags
    .replace(/!\[.*?\]\(.*?\)/g, "") // remove images
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // simplify links
    .replace(/#+\s+/g, "") // remove heading hashes
    .replace(/```[\s\S]*?```/g, "") // remove massive code blocks
    .replace(/\r?\n\s*\r?\n/g, "\n") // collapse newlines
    .trim();
}

async function syncGitHubActivity(username = GITHUB_USERNAME) {
  const db = await getDb();
  console.log(`[GitHub Deep Sync] Scanning all repositories for user: ${username}...`);

  // 1. Fetch all public repos (up to 100)
  const reposUrl = `https://api.github.com/users/${username}/repos?sort=updated&per_page=100`;
  const repos = await fetchJSON(reposUrl);

  // 2. Fetch recent user events (commits / pushes across all repos)
  let events = [];
  try {
    const eventsUrl = `https://api.github.com/users/${username}/events?per_page=30`;
    events = await fetchJSON(eventsUrl);
  } catch (e) {
    console.warn("[GitHub Deep Sync] Could not fetch user events, continuing:", e.message);
  }

  const pushEventsByRepo = {};
  for (const event of events) {
    if (event.type === "PushEvent" && event.payload?.commits) {
      const repoName = event.repo.name.split("/")[1] || event.repo.name;
      if (!pushEventsByRepo[repoName]) {
        pushEventsByRepo[repoName] = [];
      }
      for (const c of event.payload.commits) {
        if (c.message && !pushEventsByRepo[repoName].includes(c.message)) {
          pushEventsByRepo[repoName].push(c.message);
        }
      }
    }
  }

  let syncedCount = 0;
  const syncedRepos = [];
  const repoInventory = [];

  for (const repo of repos) {
    // Skip forks unless desired
    if (repo.fork) continue;

    const repoKey = `${username}/${repo.name}`;
    const lastUpdated = repo.updated_at;

    // Check if we already have an up-to-date rich memory for this repo version
    const existing = await db.collection("memories").findOne({
      type: "github",
      "metadata.repoKey": repoKey,
      "metadata.updatedAt": lastUpdated,
      "metadata.schemaVersion": 2,
    });

    // Record repository into the active inventory
    repoInventory.push({
      name: repo.name,
      repoKey,
      description: repo.description || "",
      language: repo.language || "General Software",
      topics: repo.topics || [],
      url: repo.html_url,
      updatedAt: lastUpdated,
    });

    if (existing) {
      continue; // already indexed this exact state with rich details
    }

    console.log(`[GitHub Deep Sync] Indexing technical details for: ${repo.name}...`);

    // Fetch README if available
    let readmeText = "";
    try {
      const rawReadme = await fetchRaw(`https://api.github.com/repos/${repoKey}/readme`);
      if (rawReadme) {
        const cleaned = cleanMarkdown(rawReadme);
        readmeText = cleaned.slice(0, 1500); // Take most informative overview
      }
    } catch (readmeErr) {
      // README is optional
    }

    // Fetch top-level file structure
    let fileStructure = [];
    try {
      const contents = await fetchJSON(`https://api.github.com/repos/${repoKey}/contents`);
      if (Array.isArray(contents)) {
        fileStructure = contents.map((c) => c.name).slice(0, 15);
      }
    } catch (contentsErr) {}

    const recentCommits = (pushEventsByRepo[repo.name] || []).slice(0, 3);
    const commitsText = recentCommits.length
      ? `Recent commit activities: ${recentCommits.join("; ")}`
      : "";

    const topicsText = repo.topics && repo.topics.length ? `Topics: ${repo.topics.join(", ")}` : "";
    const filesText = fileStructure.length ? `Key Files/Modules: ${fileStructure.join(", ")}` : "";

    const memoryContent = [
      `GitHub Project: ${repo.name}`,
      repo.language ? `Primary Tech/Language: ${repo.language}` : "",
      repo.description ? `Project Overview: ${repo.description}` : "",
      topicsText,
      filesText,
      readmeText ? `Technical Documentation / README Overview:\n${readmeText}` : "",
      commitsText,
      `Repository URL: ${repo.html_url}`,
    ]
      .filter(Boolean)
      .join("\n");

    // Remove older memory records for this repo so vector store stays clean
    await db.collection("memories").deleteMany({
      type: "github",
      "metadata.repoKey": repoKey,
    });

    await addMemory(memoryContent, "github", `github:${repoKey}`, {
      repoKey,
      repoName: repo.name,
      repoUrl: repo.html_url,
      language: repo.language,
      topics: repo.topics || [],
      updatedAt: lastUpdated,
      hasReadme: Boolean(readmeText),
      schemaVersion: 2,
    });

    syncedCount++;
    syncedRepos.push(repo.name);
  }

  // Update repository catalogue in MongoDB so agent knows full portfolio
  try {
    await db.collection("portfolio_catalog").updateOne(
      { _id: "github_portfolio" },
      {
        $set: {
          username,
          repos: repoInventory,
          totalRepos: repoInventory.length,
          lastSyncedAt: new Date(),
        },
      },
      { upsert: true }
    );
  } catch (catErr) {
    console.warn("[GitHub Deep Sync] Could not save portfolio catalog:", catErr.message);
  }

  console.log(
    `[GitHub Deep Sync] Complete. Synced ${syncedCount} updated repos. Portfolio contains ${repoInventory.length} total projects.`
  );
  return { syncedCount, syncedRepos, totalPortfolio: repoInventory.length };
}

// Allow direct execution: node github-sync.js
if (require.main === module) {
  syncGitHubActivity()
    .then((result) => {
      console.log(`[GitHub Deep Sync] Success!`, result);
      process.exit(0);
    })
    .catch((err) => {
      console.error("[GitHub Deep Sync] Failed:", err);
      process.exit(1);
    });
}

module.exports = { syncGitHubActivity };

