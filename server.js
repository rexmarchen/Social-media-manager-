/**
 * server.js
 * ---------
 * One always-on process that:
 *   1. Listens for Telegram commands (webhook)
 *   2. Auto-posts on an internal schedule (node-cron)
 *   3. Lets you turn that schedule on/off from Telegram
 *
 * Telegram commands:
 *   /post <topic>   - generate + publish immediately, regardless of schedule
 *   /schedule on     - enable automatic scheduled posting
 *   /schedule off    - disable automatic scheduled posting
 *   /status          - show whether the schedule is on, and the next topic
 *   /help            - list commands
 *
 * Required environment variables:
 *   TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID
 *   GEMINI_API_KEY, LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN
 *
 * Optional:
 *   TIMEZONE - defaults to "Asia/Kolkata" (IST)
 *   CRON_SCHEDULE - defaults to "30 19 * * *" (daily at 7:30 PM IST / 19:30)
 */

const express = require("express");
require("dotenv").config();
const cron = require("node-cron");
const fs = require("fs");
const path = require("path");
const { runAgentForTopic, generateAutonomousPost } = require("./agent-core");
const { runSuperBrainDailyCycle, trainSuperBrain, autoHealAndExecute } = require("./super-brain");
const { getAllRepositories } = require("./ai-researcher");
const { addMemory, getRecentMemories, loadState, saveState } = require("./mongo-store");
const { syncGitHubActivity } = require("./github-sync");
const {
  getLatestGitHubActivity,
  generateAndPublishGitHubPost,
  checkAndAutoPostGitHub,
} = require("./github-monitor");
const { runJobMonitor } = require("./job-monitor");
const {
  runCommentCampaign,
  generateInsightfulComment,
  publishLinkedInComment,
  extractUrnFromUrl,
  sendDailyTelegramCommentAudit,
  getDailyCommentReport,
  formatTelegramReportMessage,
} = require("./comment-campaign");

const app = express();
app.use(express.json());

const TELEGRAM_API = `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;
const TOPICS_PATH = path.join(__dirname, "topics.json");
const STATE_PATH = path.join(__dirname, "state.json");
const TIMEZONE = process.env.TIMEZONE || "Asia/Kolkata";
const CRON_SCHEDULE = process.env.CRON_SCHEDULE || "30 19 * * *"; // Daily at 7:30 PM IST

// Persisted schedule toggle (in-memory cache synced with MongoDB Atlas)
let scheduleEnabled = true;

// Initialize state from MongoDB on startup
loadState({ lastIndex: -1, scheduleEnabled: true })
  .then((state) => {
    scheduleEnabled = state.scheduleEnabled !== false; // default true
    console.log(
      `[Server] State loaded from MongoDB. Schedule: ${scheduleEnabled ? "ON" : "OFF"}, Last Index: ${state.lastIndex}`
    );
  })
  .catch((err) => {
    console.error("[Server] WARNING: Failed to load state from MongoDB:", err.message);
    console.warn("[Server] Defaulting to scheduleEnabled=true");
    scheduleEnabled = true; // safe default
  });

function loadJSON(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function saveJSON(filePath, data) {
  try {
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
  } catch {}
}

async function getNextTopic() {
  const topics = loadJSON(TOPICS_PATH, []);
  if (topics.length === 0) throw new Error("topics.json is empty.");
  const localState = loadJSON(STATE_PATH, { lastIndex: -1 });
  const cloudState = await loadState(localState);
  const nextIndex = (cloudState.lastIndex + 1) % topics.length;
  return { topic: topics[nextIndex], nextIndex };
}

async function advanceTopic(nextIndex) {
  saveJSON(STATE_PATH, { lastIndex: nextIndex });
  await saveState({ lastIndex: nextIndex });
}

async function sendTelegramMessage(chatId, text) {
  await fetch(`${TELEGRAM_API}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

// ---------- Background Memory Sync: Keep MongoDB updated every 30 mins (Silent, No Posting) ----------

// ---------- Background GitHub Push Watcher & Memory Sync (Every 15 mins) ----------

cron.schedule("*/15 * * * *", async () => {
  try {
    console.log("[Background Sync] Updating MongoDB memory with latest GitHub repos...");
    await syncGitHubActivity();

    if (scheduleEnabled) {
      const autoPostResult = await checkAndAutoPostGitHub();
      if (autoPostResult && autoPostResult.status === "published") {
        console.log(`[AutoPost] Successfully published GitHub push post to LinkedIn! ID: ${autoPostResult.postId}`);
        if (process.env.TELEGRAM_OWNER_ID) {
          await sendTelegramMessage(
            process.env.TELEGRAM_OWNER_ID,
            `🚀 Auto-posted new GitHub push to LinkedIn!\nProject: ${autoPostResult.activity.repoName}\nCommit: "${autoPostResult.activity.commitMessage}"\n\n"${autoPostResult.postText}"`
          );
        }
      }
    }
  } catch (err) {
    console.warn("[Background Monitor Warning]", err.message);
  }
});

// ---------- Background Job & Internship Watchdog (< 12h) ----------
const JOB_CRON = process.env.JOB_ALERT_CRON_SCHEDULE || "0 */3 * * *";
cron.schedule(JOB_CRON, async () => {
  try {
    console.log("[Job Watchdog] Scheduled check for fresh tech jobs & internships (< 12h)...");
    await runJobMonitor();
  } catch (err) {
    console.warn("[Job Watchdog Warning]", err.message);
  }
});

const activePostingUsers = new Set();
let activeRetryTimeout = null;

async function triggerDailyPost(reason = "Daily Run", forcePost = false, options = {}) {
  const userKey = String(options.userId || options.authorUrn || options.authorName || 'default');
  if (!scheduleEnabled && !forcePost) {
    console.log(`[${reason}] Skipped for ${userKey} — schedule is currently off.`);
    return { status: "skipped_schedule_off", userId: userKey };
  }

  if (activePostingUsers.has(userKey)) {
    console.log(`[${reason}] Another operation is currently in progress for user ${userKey}. Skipping duplicate.`);
    return { status: "in_progress", userId: userKey };
  }

  activePostingUsers.add(userKey);
  try {
    console.log(`[${reason}] Triggering Super Brain Autonomous Engine for user ${userKey}...`);
    const result = await runSuperBrainDailyCycle(forcePost, options);
    return result;
  } catch (err) {
    console.error(`[${reason}] Super Brain cycle encountered fatal error for user ${userKey}:`, err.message);
    throw err;
  } finally {
    activePostingUsers.delete(userKey);
  }
}

// ---------- Daily Scheduled Auto-Posting (Autonomous AI Multi-Repo RAG) ----------

cron.schedule(
  CRON_SCHEDULE,
  async () => {
    console.log(`[Daily Cron] Scheduled time reached (${CRON_SCHEDULE} ${TIMEZONE}). Triggering guaranteed LinkedIn post...`);
    try {
      await triggerDailyPost("Daily Cron", true);
    } catch (err) {
      console.error("[Daily Cron] Error during scheduled post:", err.message);
    }
  },
  {
    timezone: TIMEZONE,
  }
);

// ---------- Daily 5:00 AM IST Telegram Comment Audit Report ----------
// Strictly dispatches full audit with direct post links to verify comments
cron.schedule(
  "0 5 * * *",
  async () => {
    console.log("[Comment Audit Watchdog] 5:00 AM IST: Dispatching Daily LinkedIn Comment Audit Report to Telegram...");
    try {
      await sendDailyTelegramCommentAudit(24);
    } catch (err) {
      console.error("[Comment Audit Warning] Failed to dispatch 5 AM report:", err.message);
    }
  },
  {
    timezone: TIMEZONE,
  }
);

// ---------- Telegram Message Handler & Dispatcher ----------

async function handleTelegramMessage(message) {
  if (!message || !message.text) return;

  const senderId = String(message.from.id);
  const chatId = message.chat.id;
  const rawText = message.text.trim();
  // Strip bot mention e.g. /sync@MyBot -> /sync
  const text = rawText.replace(/@\w+/g, "").trim();
  const lower = text.toLowerCase();

  if (senderId !== process.env.TELEGRAM_OWNER_ID) {
    await sendTelegramMessage(chatId, "This bot is private — you're not authorized to use it.");
    return;
  }

  if (lower === "/help" || lower === "/start") {
    await sendTelegramMessage(
      chatId,
      "🤖 *Super Brain LinkedIn Automation Commands*:\n\n" +
        "• /post - autonomously research repos, pick an interesting project & publish\n" +
        "• /post <repo_or_topic> - publish about a specific project or topic (e.g. /post REXAI)\n" +
        "• /post github - immediately post your latest GitHub commit\n" +
        "• /train - run Super Brain self-training suite & verify self-healing reflexes\n" +
        "• /repos - view all indexed repositories in your portfolio\n" +
        "• /sync - sync all GitHub repos & READMEs into cloud vector memory\n" +
        "• /sync force - force re-indexing of all repositories\n" +
        "• /learn <text> - save what you learned or researched today\n" +
        "• /project <text> - log a project or technical milestone\n" +
        "• /jobs - check & email fresh tech jobs & internships (< 12h)\n" +
        "• /memory - show latest memories stored in MongoDB cloud\n" +
        "• /comment <post_url> - generate & publish a smart human comment on any LinkedIn post\n" +
        "• /comments - view full audit report with direct links to all commented posts\n" +
        "• /schedule on/off - toggle daily automated posting\n" +
        "• /status - show current schedule and posting status"
    );
    return;
  }

  if (lower === "/train") {
    await sendTelegramMessage(chatId, "🧠 *Super Brain Self-Training Initiated*...\nRunning multi-pass fault simulation & self-healing reflex suite.");
    try {
      const trainRes = await trainSuperBrain();
      await sendTelegramMessage(
        chatId,
        `✅ *Super Brain Self-Training Complete!*\n\n` +
          `• Reflexes Passed: ${trainRes.passed}/${trainRes.total}\n` +
          `• Cumulative Self-Healing Recipes: ${trainRes.cumulativeRecipes}\n` +
          `• Status: Autonomous self-healing & 1-day gap logic 100% operational.`
      );
    } catch (trainErr) {
      await sendTelegramMessage(chatId, `❌ Training error: ${trainErr.message}`);
    }
    return;
  }

  if (lower === "/status") {
    let gitInfo = "No GitHub push found";
    try {
      const act = await getLatestGitHubActivity();
      if (act) {
        gitInfo = `${act.repoName} ("${act.commitMessage.slice(0, 50)}")`;
      }
    } catch {}

    const state = await loadState();
    const lastPosted = state.lastPostedAt ? new Date(state.lastPostedAt).toLocaleString() : "None recorded yet";

    await sendTelegramMessage(
      chatId,
      `📊 *Agent Status*:\n\n` +
        `• Schedule: ${scheduleEnabled ? "🟢 ON (Daily Auto-Poster Active)" : "🔴 OFF"}\n` +
        `• Posting Time: 7:30 PM (Window: 7:00 PM - 8:00 PM ${TIMEZONE})\n` +
        `• Cron Schedule: ${CRON_SCHEDULE} (${TIMEZONE})\n` +
        `• Last Post Published: ${lastPosted}\n` +
        `• Latest GitHub Push: ${gitInfo}\n` +
        `• Database: MongoDB Atlas (Connected)`
    );
    return;
  }

  if (lower === "/schedule on") {
    scheduleEnabled = true;
    await saveState({ scheduleEnabled: true });
    await sendTelegramMessage(chatId, "✅ Daily automated posting and GitHub push watcher turned ON.");
    return;
  }

  if (lower === "/schedule off") {
    scheduleEnabled = false;
    await saveState({ scheduleEnabled: false });
    await sendTelegramMessage(chatId, "⏸️ Scheduled posting turned OFF.");
    return;
  }

  // Command to trigger Tech Job & Internship Watchdog on demand
  if (lower === "/jobs" || lower === "/jobs check") {
    await sendTelegramMessage(chatId, "🔍 Scanning LinkedIn for tech jobs & internships posted strictly under 12 hours...");
    try {
      const result = await runJobMonitor();
      await sendTelegramMessage(
        chatId,
        `📬 *Job Watchdog Report*:\n\n` +
          `• Fresh Positions Found (< 12h): ${result.scanned}\n` +
          `• New Unseen Postings: ${result.newJobsCount}\n` +
          `• Email Notification: ${result.emailSent ? "Delivered to your inbox ✅" : (result.newJobsCount === 0 ? "No new unnotified postings" : "SMTP Pending / Dry-run")}`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `❌ Job watchdog failed: ${err.message}`);
    }
    return;
  }

  // Command to post the latest GitHub commit immediately
  if (lower === "/post github" || lower === "/post latest") {
    await sendTelegramMessage(chatId, "🔍 Analyzing your latest GitHub push, drafting post, and generating visual...");
    try {
      const result = await generateAndPublishGitHubPost();
      await sendTelegramMessage(
        chatId,
        `🚀 Published to LinkedIn!${result.hadImage ? " (with photo)" : ""}\n\n` +
          `Project: ${result.activity.repoName}\n` +
          `Commit: "${result.activity.commitMessage}"\n` +
          `Post ID: ${result.postId}\n\n` +
          `"${result.postText}"`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `❌ Failed to post GitHub update: ${err.message}`);
    }
    return;
  }

  // Command to comment on an external LinkedIn post
  if (lower.startsWith("/comment")) {
    const rawTarget = text.replace(/^\/comment\s*/i, "").trim();
    if (!rawTarget) {
      await sendTelegramMessage(chatId, "Usage: /comment <linkedin_post_url_or_urn>");
      return;
    }

    const urn = extractUrnFromUrl(rawTarget);
    if (!urn) {
      await sendTelegramMessage(chatId, "❌ Invalid LinkedIn post URL or URN format. Example: https://www.linkedin.com/posts/activity-724...");
      return;
    }

    await sendTelegramMessage(chatId, `🧠 Reading target post and crafting human-like technical insight...`);
    try {
      const commentText = await generateInsightfulComment(
        `LinkedIn Post Reference: ${rawTarget}. Provide practical, collegial technical commentary.`,
        { authorName: "Apurav Sharma", targetRole: "Software / Full-Stack Engineer" }
      );

      await sendTelegramMessage(chatId, `💬 *Drafted Comment:*\n\n"${commentText}"\n\nPublishing to LinkedIn...`);
      const commentId = await publishLinkedInComment(urn, commentText);
      await sendTelegramMessage(chatId, `✅ Successfully commented on post!\nComment ID: ${commentId}`);
    } catch (commentErr) {
      await sendTelegramMessage(chatId, `❌ Failed to publish comment: ${commentErr.message}`);
    }
    return;
  }

  // On-demand command to view the comment audit report
  if (lower === "/comments" || lower === "/report" || lower === "/comments_report") {
    await sendTelegramMessage(chatId, "🔍 Generating LinkedIn Comment Audit Report with direct clickable post links...");
    try {
      const entries = getDailyCommentReport(48); // last 48 hours for full visibility
      const reportText = formatTelegramReportMessage(entries);
      await sendTelegramMessage(chatId, reportText);
    } catch (reportErr) {
      await sendTelegramMessage(chatId, `❌ Failed to generate report: ${reportErr.message}`);
    }
    return;
  }

  if (lower.startsWith("/learn")) {
    const note = text.replace(/^\/learn\s*/i, "").trim();
    if (!note) {
      await sendTelegramMessage(chatId, "Usage: /learn <what you learned or researched>");
      return;
    }
    await sendTelegramMessage(chatId, "Embedding and saving to MongoDB Atlas cloud memory...");
    try {
      await addMemory(note, "learning", "telegram");
      await sendTelegramMessage(chatId, "Saved to cloud memory! 🧠 I will use this context when drafting your posts.");
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to save memory: ${err.message}`);
    }
    return;
  }

  if (lower.startsWith("/project")) {
    const note = text.replace(/^\/project\s*/i, "").trim();
    if (!note) {
      await sendTelegramMessage(chatId, "Usage: /project <project or milestone details>");
      return;
    }
    await sendTelegramMessage(chatId, "Embedding and saving project milestone to cloud memory...");
    try {
      await addMemory(note, "project", "telegram");
      await sendTelegramMessage(chatId, "Project milestone saved! 🚀 I will feature this in upcoming posts.");
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to save project: ${err.message}`);
    }
    return;
  }

  if (lower === "/sync" || lower.startsWith("/sync ")) {
    const isForce = lower.includes("force") || lower.includes("refresh") || lower.includes("all");
    await sendTelegramMessage(chatId, `🔄 Syncing public GitHub repositories${isForce ? " (force full refresh)" : ""}...`);
    try {
      const result = await syncGitHubActivity(process.env.GITHUB_USERNAME || "rexmarchen", isForce);
      if (result.syncedCount > 0) {
        await sendTelegramMessage(
          chatId,
          `✅ GitHub sync complete!\nIndexed ${result.syncedCount} updated repos:\n${result.syncedRepos.map((r) => `• ${r}`).join("\n")}\n\n📁 Total Portfolio: ${result.totalPortfolio} projects in memory.`
        );
      } else {
        await sendTelegramMessage(
          chatId,
          `✅ All ${result.totalPortfolio} GitHub repositories are already indexed & up to date in vector memory!\n\nIndexed projects:\n${(result.allRepos || []).map((r) => `• ${r}`).join("\n")}\n\n💡 Use "/sync force" to re-embed all READMEs from scratch.`
        );
      }
    } catch (err) {
      await sendTelegramMessage(chatId, `❌ GitHub sync failed: ${err.message}`);
    }
    return;
  }

  if (lower === "/memory" || lower === "/memories") {
    try {
      const recent = await getRecentMemories(5);
      if (!recent.length) {
        await sendTelegramMessage(chatId, "No memories stored yet. Use /learn or /sync github to add memories.");
        return;
      }
      const summary = recent
        .map((m, i) => `${i + 1}. [${m.type.toUpperCase()}] ${m.content.slice(0, 120)}...`)
        .join("\n\n");
      await sendTelegramMessage(chatId, `Latest memories in MongoDB Atlas:\n\n${summary}`);
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to fetch memories: ${err.message}`);
    }
    return;
  }

  if (lower === "/repos" || lower === "/projects") {
    try {
      const repos = await getAllRepositories();
      const list = repos.map((r, i) => `${i + 1}. ${r.name} (${r.language})`).join("\n");
      await sendTelegramMessage(
        chatId,
        `📁 Indexed Repositories (${repos.length} total):\n\n${list}\n\nUse /post <repo_name> to feature any specific project, or /post to let the AI decide!`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to load repositories: ${err.message}`);
    }
    return;
  }

  if (lower === "/post" || lower === "/post auto") {
    await sendTelegramMessage(
      chatId,
      "🤖 Autonomous AI Researcher active: inspecting portfolio, selecting an interesting project, retrieving RAG context, and drafting post..."
    );
    try {
      const result = await generateAutonomousPost();
      await sendTelegramMessage(
        chatId,
        `🚀 Published to LinkedIn!${result.hadImage ? " (with custom image)" : ""}\n\n` +
          `Project: ${result.repoName}\n` +
          `Topic: ${result.topicTitle}\n` +
          `Post ID: ${result.postId}\n\n` +
          `"${result.postText}"`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to generate post: ${err.message}`);
    }
    return;
  }

  if (lower.startsWith("/post")) {
    let topicOrRepo = text.replace(/^\/post\s*/i, "").trim();
    // Strip wrapping angle brackets, quotes, and punctuation
    topicOrRepo = topicOrRepo.replace(/^[<"'\s]+|[>"'\s]+$/g, "").trim();

    if (!topicOrRepo) {
      await sendTelegramMessage(chatId, "Usage: /post, /post <repo_name>, or /post <custom topic>");
      return;
    }

    try {
      const allRepos = await getAllRepositories();
      const matchedRepo = allRepos.find(
        (r) => r.name.toLowerCase() === topicOrRepo.toLowerCase()
      );

      let result;
      if (matchedRepo) {
        await sendTelegramMessage(
          chatId,
          `Researching project "${matchedRepo.name}" with RAG and drafting an authentic post...`
        );
        result = await generateAutonomousPost(matchedRepo.name);
      } else {
        await sendTelegramMessage(chatId, `Working on it — drafting a post about: "${topicOrRepo}"...`);
        result = await runAgentForTopic(topicOrRepo);
      }

      await sendTelegramMessage(
        chatId,
        `Published!${result.hadImage ? " (with image)" : ""}\nPost ID: ${result.postId}\n\n"${result.postText}"`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to post: ${err.message}`);
    }
    return;
  }

  await sendTelegramMessage(chatId, "Unrecognized command. Send /help to see what I can do.");
}

// Telegram Webhook endpoint (for cloud deployments with valid public URLs)
app.post("/telegram-webhook", async (req, res) => {
  res.sendStatus(200); // acknowledge Telegram immediately
  if (req.body && req.body.message) {
    handleTelegramMessage(req.body.message).catch((err) => {
      console.error("[Telegram Webhook Error]", err.message);
    });
  }
});

// ---------- Telegram Long Polling (Local execution & fallback) ----------
let pollingActive = false;
let pollingOffset = 0;

async function startTelegramPolling() {
  if (pollingActive) return;
  if (!process.env.TELEGRAM_BOT_TOKEN) {
    console.warn("[Telegram Bot] Cannot start polling: TELEGRAM_BOT_TOKEN is missing.");
    return;
  }

  pollingActive = true;
  console.log("[Telegram Bot] Initializing Long Polling mode (clearing stale webhooks)...");

  try {
    const delRes = await fetch(`${TELEGRAM_API}/deleteWebhook?drop_pending_updates=false`);
    const delData = await delRes.json();
    if (delData.ok) {
      console.log("[Telegram Bot] Webhook successfully cleared. Long polling is now ACTIVE!");
    } else {
      console.warn("[Telegram Bot] deleteWebhook returned:", delData.description);
    }
  } catch (err) {
    console.warn("[Telegram Bot] Failed to clear webhook:", err.message);
  }

  console.log("🤖 [Telegram Bot] Listening for messages directly (Local & Cloud compatible)...");

  async function pollLoop() {
    if (!pollingActive) return;
    try {
      const pollUrl = `${TELEGRAM_API}/getUpdates?offset=${pollingOffset}&timeout=25`;
      const res = await fetch(pollUrl);
      if (res.ok) {
        const data = await res.json();
        if (data.ok && Array.isArray(data.result)) {
          for (const update of data.result) {
            pollingOffset = update.update_id + 1;
            if (update.message) {
              handleTelegramMessage(update.message).catch((err) =>
                console.error("[Telegram Poll Handler Error]", err.message)
              );
            }
          }
        }
      } else {
        const errText = await res.text();
        console.warn(`[Telegram Poll] HTTP ${res.status}: ${errText}`);
        await new Promise((r) => setTimeout(r, 4000));
      }
    } catch (err) {
      // Temporary network interruption or timeout
      await new Promise((r) => setTimeout(r, 3000));
    }

    if (pollingActive) {
      setImmediate(pollLoop);
    }
  }

  pollLoop();
}

app.get("/", (req, res) => res.send("LinkedIn agent server is running."));
app.get("/health", (req, res) =>
  res.json({
    status: "ok",
    uptime: Math.round(process.uptime()),
    timestamp: new Date(),
  })
);

// External trigger route for cron services (e.g. cron-job.org / GitHub Actions / curl)
app.all("/trigger-daily", async (req, res) => {
  // Default to force=true so webhook crons always guarantee publishing, unless ?force=false is passed
  const force = req.query.force !== "false" && req.body?.force !== false;
  try {
    const options = {
      accessToken: req.body?.accessToken || req.headers['x-linkedin-token'] || null,
      authorUrn: req.body?.authorUrn || req.body?.personUrn || null,
      topic: req.body?.topic || req.query.topic || null,
      userId: req.body?.userId || null,
      authorName: req.body?.authorName || null,
      isOwner: req.body?.isOwner !== undefined ? Boolean(req.body.isOwner) : null,
      targetRole: req.body?.targetRole || null,
      githubUsername: req.body?.githubUsername || null
    };
    const result = await triggerDailyPost("External Webhook Trigger", force, options);
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get("/sync-github", async (req, res) => {
  try {
    const force = req.query.force === "true";
    const result = await syncGitHubActivity(process.env.GITHUB_USERNAME || "rexmarchen", force);
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Single comment trigger route
app.post("/comment", async (req, res) => {
  try {
    const { url, postUrn, postText, authorName, targetRole, accessToken, authorUrn } = req.body || {};
    const urn = extractUrnFromUrl(url || postUrn);
    if (!urn) {
      return res.status(400).json({ ok: false, error: "Valid url or postUrn is required." });
    }

    const commentText = await generateInsightfulComment(postText || url || "Tech engineering post", {
      authorName: authorName || "Apurav Sharma",
      targetRole: targetRole || "Software / Full-Stack Engineer"
    });

    const commentId = await publishLinkedInComment(urn, commentText, {
      accessToken,
      authorUrn
    });

    res.json({ ok: true, urn, commentText, commentId });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Automated safe batch campaign route for Apurav or any user
app.post("/comment-campaign", async (req, res) => {
  try {
    const { posts, authorName, targetRole, dailyLimit, dryRun, accessToken, authorUrn } = req.body || {};
    const options = {
      authorName: authorName || "Apurav Sharma",
      targetRole: targetRole || "Software / Full-Stack Engineer",
      dailyLimit: dailyLimit || 6,
      dryRun: Boolean(dryRun),
      accessToken,
      authorUrn
    };

    // Run campaign with built-in human safety jitter & deduplication
    const result = await runCommentCampaign(posts || [], options);
    res.json({ ok: true, result });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// External trigger route to manually trigger the 5 AM Telegram report anytime
app.all("/comment-report", async (req, res) => {
  try {
    const hours = parseInt(req.query.hours || req.body?.hours || 24, 10);
    const sent = await sendDailyTelegramCommentAudit(hours);
    const entries = getDailyCommentReport(hours);
    res.json({ ok: true, sent, entriesCount: entries.length, entries });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Global anti-crash handlers: prevent unhandled errors from terminating the server process
process.on("unhandledRejection", (reason) => {
  console.error("[Anti-Crash] Unhandled Rejection caught:", reason);
});

process.on("uncaughtException", (err) => {
  console.error("[Anti-Crash] Uncaught Exception caught:", err);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`Listening on port ${PORT}. Cron: ${CRON_SCHEDULE} (${TIMEZONE})`);

  const customWebhook = process.env.WEBHOOK_URL;
  const externalUrl = process.env.RENDER_EXTERNAL_URL;

  if (customWebhook) {
    const fullWebhookUrl = `${customWebhook.replace(/\/$/, "")}/telegram-webhook`;
    console.log(`[Telegram] Setting webhook to ${fullWebhookUrl}...`);
    try {
      await fetch(`${TELEGRAM_API}/setWebhook?url=${encodeURIComponent(fullWebhookUrl)}`);
    } catch (e) {
      console.warn("[Telegram] Failed to set webhook:", e.message);
    }
  } else {
    // Default to Long Polling for direct local & self-hosted reliability (no suspended Render webhooks)
    startTelegramPolling();
  }

  // Keep-alive self ping — only if a live RENDER_EXTERNAL_URL is explicitly provided
  if (externalUrl) {
    const PING_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
    setInterval(() => {
      fetch(`${externalUrl}/health`)
        .then((r) => { if (!r.ok) console.warn(`[Keep-Alive] Ping returned status ${r.status}`); })
        .catch((err) => console.warn(`[Keep-Alive] Ping failed: ${err.message}`));
    }, PING_INTERVAL_MS);
    console.log(`[Keep-Alive] Self-ping enabled every 5 minutes → ${externalUrl}/health`);
  }
});

