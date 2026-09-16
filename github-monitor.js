/**
 * github-monitor.js
 * -----------------
 * Detects new code pushes to GitHub (rexmarchen), generates an authentic
 * developer post about what was built/updated, uploads a project photo,
 * and publishes it to LinkedIn automatically.
 */

const { generatePost, generateImage, uploadImageToLinkedIn, publishPost } = require("./agent-core");
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
 * Generate an authentic LinkedIn post for a GitHub push and publish it
 */
async function generateAndPublishGitHubPost(username = GITHUB_USERNAME) {
  const activity = await getLatestGitHubActivity(username);
  if (!activity) {
    throw new Error("No recent GitHub activity found.");
  }

  const topic = `New code shipped to ${activity.repoName}: ${activity.commitMessage}`;
  const context = `
AUTHOR GITHUB ACTIVITY:
- Repository: ${activity.repoFullName}
- Primary Tech / Language: ${activity.language}
- Project Purpose: ${activity.description || "Open source developer tool"}
- Latest Commit: ${activity.commitMessage}
- Repository Link: ${activity.repoUrl}
`;

  console.log(`[GitHub Agent] Drafting LinkedIn post for ${activity.repoName}...`);
  const { post_text, needs_image, image_prompt } = await generatePost(topic, context);

  // Smart image handling: NO static banner photos!
  // Only generate a custom graphic if the AI genuinely determines visual aid is needed for this topic
  let imageUrn = null;
  if (needs_image && image_prompt) {
    console.log(`[GitHub Agent] AI determined a visual diagram adds value. Generating unique graphic...`);
    try {
      const imageBuffer = await generateImage(image_prompt);
      imageUrn = await uploadImageToLinkedIn(imageBuffer);
      console.log(`[GitHub Agent] Custom image uploaded to LinkedIn. URN: ${imageUrn}`);
    } catch (imgErr) {
      console.warn("[GitHub Agent] Optional image generation skipped:", imgErr.message);
    }
  } else {
    console.log(`[GitHub Agent] Clean text post selected (no unnecessary photo attached).`);
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
      { commitSha: activity.commitSha, postId, repoName: activity.repoName }
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
