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
const { runAgentForTopic } = require("./agent-core");
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

cron.schedule("*/30 * * * *", async () => {
  try {
    console.log("[Background Sync] Updating MongoDB memory with latest GitHub repos...");
    await syncGitHubActivity();
  } catch (err) {
    console.warn("[Background Sync Warning]", err.message);
  }
});


// ---------- Daily Scheduled Auto-Posting (GitHub-First) ----------

cron.schedule(CRON_SCHEDULE, async () => {
  if (!scheduleEnabled) {
    console.log("Scheduled run skipped — schedule is currently off.");
    return;
  }
  try {
    // Check if there is GitHub activity to post about first (prioritize real builds)
    const latestActivity = await getLatestGitHubActivity();
    let result;

    if (latestActivity) {
      console.log(`[Daily Run] Posting about latest GitHub project: ${latestActivity.repoName}`);
      result = await generateAndPublishGitHubPost();
    } else {
      const { topic, nextIndex } = await getNextTopic();
      console.log(`[Daily Run] Posting topic: ${topic}`);
      result = await runAgentForTopic(topic);
      await advanceTopic(nextIndex);
    }

    console.log(`Scheduled post published. ID: ${result.postId}`);
    if (process.env.TELEGRAM_OWNER_ID) {
      await sendTelegramMessage(
        process.env.TELEGRAM_OWNER_ID,
        `Scheduled post published.${result.hadImage ? " (with photo)" : ""}\n\n"${result.postText}"`
      );
    }
  } catch (err) {
    console.error("Scheduled post failed:", err.message);
    if (process.env.TELEGRAM_OWNER_ID) {
      await sendTelegramMessage(process.env.TELEGRAM_OWNER_ID, `Scheduled post failed: ${err.message}`);
    }
  }
});

// ---------- Telegram Webhook ----------

app.post("/telegram-webhook", async (req, res) => {
  res.sendStatus(200); // acknowledge Telegram immediately

  const message = req.body.message;
  if (!message || !message.text) return;

  const senderId = String(message.from.id);
  const chatId = message.chat.id;
  const text = message.text.trim();

  if (senderId !== process.env.TELEGRAM_OWNER_ID) {
    await sendTelegramMessage(chatId, "This bot is private — you're not authorized to use it.");
    return;
  }

  if (text === "/help" || text === "/start") {
    await sendTelegramMessage(
      chatId,
      "Commands:\n" +
        "/post github - immediately post your latest GitHub project & commit with photo\n" +
        "/post <topic> - generate and publish a specific custom topic\n" +
        "/learn <text> - save what you learned or researched today\n" +
        "/project <text> - log a project or technical milestone\n" +
        "/sync github - sync your latest GitHub repos & commits\n" +
        "/memory - show latest memories stored in cloud\n" +
        "/schedule on - enable 24/7 automatic GitHub & scheduled posting\n" +
        "/schedule off - pause automatic posting\n" +
        "/status - show current schedule state and latest GitHub commit"
    );
    return;
  }

  if (text === "/status") {
    let gitInfo = "No GitHub push found";
    try {
      const act = await getLatestGitHubActivity();
      if (act) {
        gitInfo = `${act.repoName} ("${act.commitMessage.slice(0, 50)}")`;
      }
    } catch {}

    await sendTelegramMessage(
      chatId,
      `Schedule: ${scheduleEnabled ? "ON (24/7 GitHub Push Watcher Active)" : "OFF"}\n` +
        `Cron: ${CRON_SCHEDULE}\n` +
        `Latest GitHub Project: ${gitInfo}\n` +
        `Database: MongoDB Atlas (Connected)`
    );
    return;
  }

  if (text === "/schedule on") {
    scheduleEnabled = true;
    await saveState({ scheduleEnabled: true });
    await sendTelegramMessage(chatId, "24/7 GitHub push watcher & scheduled posting turned ON (saved to cloud).");
    return;
  }

  if (text === "/schedule off") {
    scheduleEnabled = false;
    await saveState({ scheduleEnabled: false });
    await sendTelegramMessage(chatId, "Scheduled posting turned OFF (saved to cloud).");
    return;
  }

  // Command to post the latest GitHub commit with photo immediately
  if (text === "/post github" || text === "/post latest") {
    await sendTelegramMessage(chatId, "Analyzing your latest GitHub push, drafting post, and preparing photo...");
    try {
      const result = await generateAndPublishGitHubPost();
      await sendTelegramMessage(
        chatId,
        `Published to LinkedIn!${result.hadImage ? " (with photo)" : ""}\n` +
          `Project: ${result.activity.repoName}\n` +
          `Commit: "${result.activity.commitMessage}"\n` +
          `Post ID: ${result.postId}\n\n` +
          `"${result.postText}"`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `Failed to post GitHub update: ${err.message}`);
    }
    return;
  }

  if (text.startsWith("/learn")) {
    const note = text.replace("/learn", "").trim();
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

  if (text.startsWith("/project")) {
    const note = text.replace("/project", "").trim();
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

  if (text === "/sync github" || text === "/sync") {
    await sendTelegramMessage(chatId, "Syncing public GitHub repositories and commits...");
    try {
      const result = await syncGitHubActivity();
      await sendTelegramMessage(
        chatId,
        `GitHub sync complete! Synced ${result.syncedCount} projects:\n${result.syncedRepos.join("\n")}`
      );
    } catch (err) {
      await sendTelegramMessage(chatId, `GitHub sync failed: ${err.message}`);
    }
    return;
  }

  if (text === "/memory" || text === "/memories") {
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

  if (text.startsWith("/post")) {
    const topic = text.replace("/post", "").trim();
    if (!topic) {
      await sendTelegramMessage(chatId, "Usage: /post <topic> or /post github");
      return;
    }
    await sendTelegramMessage(chatId, `Working on it — drafting a post about: "${topic}"...`);
    try {
      const result = await runAgentForTopic(topic);
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

