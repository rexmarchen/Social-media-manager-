/**
 * github-monitor.js
 * -----------------
 * Detects new code pushes to GitHub (rexmarchen), generates an authentic
 * developer post about what was built/updated, uploads a project photo,
 * and publishes it to LinkedIn automatically.
 */

const { generatePost, uploadImageToLinkedIn, publishPost } = require("./agent-core");
const { getDb, loadState, saveState, addMemory } = require("./mongo-store");
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
  if (!res.ok) throw new Error(`GitHub API error (${res.status}): ${await res.text()}`);
  return res.json();
}

/**
 * Get the latest push activity from GitHub
 */
async function getLatestGitHubActivity(username = GITHUB_USERNAME) {
  const eventsUrl = `https://api.github.com/users/${username}/events?per_page=10`;
  const events = await fetchJSON(eventsUrl);

  const pushEvent = events.find((e) => e.type === "PushEvent");
  if (!pushEvent) return null;

  const repoFullName = pushEvent.repo.name; // e.g. "rexmarchen/Social-media-manager-"
  const repoName = repoFullName.split("/")[1] || repoFullName;

  // Fetch recent commits on this repo
  let commitMessage = "Shipped new code updates and improvements";
  let commitSha = "";
  try {
    const commits = await fetchJSON(`https://api.github.com/repos/${repoFullName}/commits?per_page=1`);
    if (commits && commits[0]) {
      commitSha = commits[0].sha.slice(0, 7);
      commitMessage = commits[0].commit.message;
    }
  } catch {}

  // Fetch repo metadata
  let description = "";
  let language = "Code";
  try {
    const repoInfo = await fetchJSON(`https://api.github.com/repos/${repoFullName}`);
    description = repoInfo.description || "";
    language = repoInfo.language || "Software Engineering";
  } catch {}

  return {
    eventId: pushEvent.id,
    repoName,
    repoFullName,
    repoUrl: `https://github.com/${repoFullName}`,
    description,
    language,
    commitSha,
    commitMessage,
    createdAt: pushEvent.created_at,
  };
}

/**
 * Fetch a high-resolution preview photo for the repository
 */
async function fetchProjectPhoto(repoFullName) {
  try {
    const cardUrl = `https://opengraph.githubassets.com/1/${repoFullName}`;
    const res = await fetch(cardUrl);
    if (res.ok) {
      const arrayBuffer = await res.arrayBuffer();
      return Buffer.from(arrayBuffer);
    }
  } catch (err) {
    console.warn("[Photo Warning] Could not fetch GitHub preview photo:", err.message);
  }
  return null;
}

/**
 * Generate an authentic LinkedIn post for a GitHub push and publish it
 */
async function generateAndPublishGitHubPost(username = GITHUB_USERNAME) {
  const activity = await getLatestGitHubActivity(username);
  if (!activity) {
    throw new Error("No recent GitHub activity found.");
  }

  const topic = `New update shipped to ${activity.repoName}`;
  const context = `
AUTHOR GITHUB ACTIVITY:
- Repository: ${activity.repoFullName}
- Primary Tech / Language: ${activity.language}
- Project Purpose: ${activity.description || "Open source developer tool"}
- Latest Commit Update: ${activity.commitMessage}
- Repository Link: ${activity.repoUrl}
`;

  // Custom prompt tailored specifically for shipping real code
  const customPrompt = `You are writing a LinkedIn post for Anshu Pal, a computer science student and software builder.
Anshu just pushed new code to his GitHub project.

PROJECT DETAILS:
- Repository: ${activity.repoName} (${activity.language})
- What it does: ${activity.description || "Developer automation and tools"}
- What was just committed/shipped: ${activity.commitMessage}
- GitHub Link: ${activity.repoUrl}

Write a compelling, authentic LinkedIn post following these rules:
- 100-170 words
- Open with what was just built or solved (not "Excited to announce")
- Sound like a real builder sharing technical lessons and implementation details
- Highlight the problem it solves and key technical decisions (languages, APIs, architecture)
- Invite feedback from other developers/engineers
- Mention that the code is open source on GitHub: ${activity.repoUrl}
- Add 3-5 relevant hashtags at the end

Respond with ONLY valid JSON:
{
  "post_text": "<the full post text>",
  "needs_image": true,
  "image_prompt": ""
}`;

  console.log(`[GitHub Agent] Drafting LinkedIn post for ${activity.repoName}...`);
  // Use generatePost
  const { post_text } = await generatePost(topic, context);

  // Fetch the official project preview photo
  console.log(`[GitHub Agent] Fetching project photo for ${activity.repoFullName}...`);
  let imageUrn = null;
  const photoBuffer = await fetchProjectPhoto(activity.repoFullName);
  if (photoBuffer) {
    try {
      imageUrn = await uploadImageToLinkedIn(photoBuffer);
      console.log(`[GitHub Agent] Photo uploaded to LinkedIn. URN: ${imageUrn}`);
    } catch (uploadErr) {
      console.warn("[Photo Upload Warning] Failed to upload photo:", uploadErr.message);
    }
  }

  // Publish post to LinkedIn
  console.log("[GitHub Agent] Publishing post to LinkedIn...");
  const postId = await publishPost(post_text, imageUrn);

  // Save to MongoDB memories so the agent remembers it forever
  try {
    await addMemory(
      `Shipped update to ${activity.repoName}: ${activity.commitMessage}. Post published: ${post_text}`,
      "github_post",
      `github:${activity.repoFullName}`,
      { commitSha: activity.commitSha, postId }
    );
    await saveState({
      lastPostedGitHubCommit: activity.commitSha,
      lastPostedGitHubEventId: activity.eventId,
      lastPostedAt: new Date(),
    });
  } catch (dbErr) {
    console.warn("Could not save post state to MongoDB:", dbErr.message);
  }

  return {
    postId,
    postText: post_text,
    hadImage: Boolean(imageUrn),
    activity,
  };
}

/**
 * Check if there is a new push on GitHub that hasn't been posted yet.
 * If new, posts it automatically!
 */
async function checkAndAutoPostGitHub(username = GITHUB_USERNAME, minCooldownHours = 12) {
  const activity = await getLatestGitHubActivity(username);
  if (!activity) return { status: "no_activity" };

  const state = await loadState({ lastPostedGitHubCommit: "", lastPostedGitHubEventId: "" });

  // 1. Check if already posted for this exact commit or event
  if (
    state.lastPostedGitHubCommit === activity.commitSha ||
    state.lastPostedGitHubEventId === activity.eventId
  ) {
    return { status: "already_posted", commitSha: activity.commitSha, repo: activity.repoName };
  }

  // 2. Minimum cooldown between automatic posts (prevents spamming if many commits are pushed)
  if (state.lastPostedAt) {
    const elapsedHours = (Date.now() - new Date(state.lastPostedAt).getTime()) / (1000 * 60 * 60);
    if (elapsedHours < minCooldownHours) {
      return {
        status: "cooldown",
        message: `Cooldown active: last post was ${elapsedHours.toFixed(1)}h ago (minimum ${minCooldownHours}h between automatic posts).`,
      };
    }
  }

  console.log(`[AutoPost] New GitHub push detected on ${activity.repoName}! Commit: ${activity.commitSha}`);
  const result = await generateAndPublishGitHubPost(username);
  return { status: "published", ...result };
}

module.exports = {
  getLatestGitHubActivity,
  generateAndPublishGitHubPost,
  checkAndAutoPostGitHub,
};
