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
 *   CRON_SCHEDULE - defaults to "0 14 * * *" (daily at 14:00 UTC)
 */

const express = require("express");
require("dotenv").config();
const cron = require("node-cron");
const fs = require("fs");
const path = require("path");
const { runAgentForTopic, generateAutonomousPost } = require("./agent-core");
const { getAllRepositories } = require("./ai-researcher");
const { addMemory, getRecentMemories, loadState, saveState } = require("./mongo-store");
const { syncGitHubActivity } = require("./github-sync");
const {
  getLatestGitHubActivity,
  generateAndPublishGitHubPost,
  checkAndAutoPostGitHub,
} = require("./github-monitor");

const app = express();
app.use(express.json());

const TELEGRAM_API = `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;
const TOPICS_PATH = path.join(__dirname, "topics.json");
const STATE_PATH = path.join(__dirname, "state.json");
const CRON_SCHEDULE = process.env.CRON_SCHEDULE || "0 14 * * *";

// Persisted schedule toggle (in-memory cache synced with MongoDB Atlas)
let scheduleEnabled = true;

// Initialize state from MongoDB on startup
loadState({ lastIndex: -1, scheduleEnabled: true })
  .then((state) => {
    scheduleEnabled = state.scheduleEnabled;
    console.log(
      `[Server] State loaded from MongoDB. Schedule: ${scheduleEnabled ? "ON" : "OFF"}, Last Index: ${state.lastIndex}`
    );
  })
  .catch(() => {});

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

async function triggerDailyPost(reason = "Daily Run") {
  if (!scheduleEnabled) {
    console.log(`[${reason}] Skipped — schedule is currently off.`);
    return { status: "skipped_schedule_off" };
  }
  try {
    console.log(`[${reason}] Triggering autonomous AI research & RAG pipeline across portfolio...`);
    const result = await generateAutonomousPost();

    console.log(`[${reason}] Scheduled post published. ID: ${result.postId}, Repo: ${result.repoName}`);
    if (process.env.TELEGRAM_OWNER_ID) {
      await sendTelegramMessage(
        process.env.TELEGRAM_OWNER_ID,
        `🚀 Scheduled post published! (Project: ${result.repoName})${result.hadImage ? " [with photo]" : ""}\n\n"${result.postText}"`
      );
    }
    return { status: "published", ...result };
  } catch (err) {
    console.error(`[${reason}] Post failed:`, err.message);
    if (process.env.TELEGRAM_OWNER_ID) {
      await sendTelegramMessage(process.env.TELEGRAM_OWNER_ID, `Scheduled post failed: ${err.message}`);
    }
    throw err;
  }
}

// ---------- Daily Scheduled Auto-Posting (Autonomous AI Multi-Repo RAG) ----------

cron.schedule(CRON_SCHEDULE, async () => {
  await triggerDailyPost("Daily Cron");
});

// ---------- Telegram Webhook ----------

app.post("/telegram-webhook", async (req, res) => {
  res.sendStatus(200); // acknowledge Telegram immediately

  const message = req.body.message;
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
      "🤖 *LinkedIn Automation Commands*:\n\n" +
        "• /post - autonomously research repos, pick an interesting project & publish\n" +
        "• /post <repo_or_topic> - publish about a specific project or topic (e.g. /post REXAI)\n" +
        "• /post github - immediately post your latest GitHub commit\n" +
        "• /repos - view all indexed repositories in your portfolio\n" +
        "• /sync - sync all GitHub repos & READMEs into cloud vector memory\n" +
        "• /sync force - force re-indexing of all repositories\n" +
        "• /learn <text> - save what you learned or researched today\n" +
        "• /project <text> - log a project or technical milestone\n" +
        "• /memory - show latest memories stored in MongoDB cloud\n" +
        "• /schedule on/off - toggle daily automated posting\n" +
        "• /status - show current schedule and posting status"
    );
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
        `• Cron Schedule: ${CRON_SCHEDULE} (UTC)\n` +
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
});

app.get("/", (req, res) => res.send("LinkedIn agent server is running."));
app.get("/health", (req, res) =>
  res.json({
    status: "ok",
    uptime: Math.round(process.uptime()),
    timestamp: new Date(),
  })
);

// External trigger route for cron services (e.g. cron-job.org / GitHub Actions / curl)
app.get("/trigger-daily", async (req, res) => {
  try {
    const result = await triggerDailyPost("External Webhook Trigger");
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

// Global anti-crash handlers: prevent unhandled errors from terminating the server process
process.on("unhandledRejection", (reason) => {
  console.error("[Anti-Crash] Unhandled Rejection caught:", reason);
});

process.on("uncaughtException", (err) => {
  console.error("[Anti-Crash] Uncaught Exception caught:", err);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Listening on port ${PORT}. Cron: ${CRON_SCHEDULE}`);

  // Keep-alive self ping if running on Render (prevents free tier sleep)
  const externalUrl = process.env.RENDER_EXTERNAL_URL || "https://social-media-manager-2-mkyg.onrender.com";
  if (externalUrl) {
    setInterval(() => {
      fetch(`${externalUrl}/health`).catch(() => {});
    }, 12 * 60 * 1000); // pings every 12 minutes
  }
});

