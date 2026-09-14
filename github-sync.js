/**
 * github-sync.js
 * --------------
 * Automatically syncs your public GitHub repositories, latest commits,
 * and project descriptions into MongoDB Atlas vector memory.
 * This gives the LinkedIn agent real, updated context about what you build.
 */

const { getDb, addMemory } = require("./mongo-store");
require("dotenv").config();

const GITHUB_USERNAME = process.env.GITHUB_USERNAME || "rexmarchen";

async function fetchJSON(url) {
  const headers = {
    "User-Agent": "linkedin-automation-agent",
    Accept: "application/vnd.github.v3+json",
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

async function syncGitHubActivity(username = GITHUB_USERNAME) {
  const db = await getDb();
  console.log(`[GitHub Sync] Fetching activity for GitHub user: ${username}...`);

  // 1. Fetch user's recent repositories
  const reposUrl = `https://api.github.com/users/${username}/repos?sort=updated&per_page=10`;
  const repos = await fetchJSON(reposUrl);

  // 2. Fetch user's recent events (commits / pushes)
  let events = [];
  try {
    const eventsUrl = `https://api.github.com/users/${username}/events?per_page=15`;
    events = await fetchJSON(eventsUrl);
  } catch (e) {
    console.warn("[GitHub Sync] Could not fetch events, continuing with repos only:", e.message);
  }

  const pushEventsByRepo = {};
  for (const event of events) {
    if (event.type === "PushEvent" && event.payload?.commits) {
      const repoName = event.repo.name.split("/")[1] || event.repo.name;
      if (!pushEventsByRepo[repoName]) {
        pushEventsByRepo[repoName] = [];
      }
      for (const c of event.payload.commits) {
        pushEventsByRepo[repoName].push(c.message);
      }
    }
  }

  let syncedCount = 0;
  const syncedRepos = [];

  for (const repo of repos) {
    // Skip forks unless desired
    if (repo.fork) continue;

    const repoKey = `${username}/${repo.name}`;
    const lastUpdated = repo.updated_at;

    // Check if we already have an up-to-date memory for this repo version
    const existing = await db.collection("memories").findOne({
      type: "github",
      "metadata.repoKey": repoKey,
      "metadata.updatedAt": lastUpdated,
    });

    if (existing) {
      continue; // already indexed this exact state
    }

    // Build rich context about the repository
    const recentCommits = (pushEventsByRepo[repo.name] || []).slice(0, 3);
    const commitsText = recentCommits.length
      ? `Recent commit activities: ${recentCommits.join("; ")}`
      : "";

    const topicsText = repo.topics && repo.topics.length ? `Topics: ${repo.topics.join(", ")}` : "";

    const memoryContent = [
      `GitHub Project: ${repo.name}`,
      repo.language ? `Primary Language: ${repo.language}` : "",
      repo.description ? `Description: ${repo.description}` : "",
      topicsText,
      commitsText,
      `GitHub Repository URL: ${repo.html_url}`,
    ]
      .filter(Boolean)
      .join(". ");

    // Remove any older record for this repo so we only keep latest
    await db.collection("memories").deleteMany({
      type: "github",
      "metadata.repoKey": repoKey,
    });

    await addMemory(memoryContent, "github", `github:${repoKey}`, {
      repoKey,
      repoName: repo.name,
      repoUrl: repo.html_url,
      language: repo.language,
      updatedAt: lastUpdated,
    });

    syncedCount++;
    syncedRepos.push(repo.name);
    console.log(`[GitHub Sync] Synced project: ${repo.name}`);
  }

  return { syncedCount, syncedRepos };
}

// Allow direct execution: node github-sync.js
if (require.main === module) {
  syncGitHubActivity()
    .then((result) => {
      console.log(`[GitHub Sync] Complete! Synced ${result.syncedCount} projects:`, result.syncedRepos);
      process.exit(0);
    })
    .catch((err) => {
      console.error("[GitHub Sync] Failed:", err);
      process.exit(1);
    });
}

module.exports = { syncGitHubActivity };
