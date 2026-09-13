# LinkedIn RAG Agent — Full Setup (Local Documents + Vector DB + Telegram)

This version reads real files from your laptop (`.txt`, `.md`, `.pdf`, `.docx`),
chunks them, embeds them with Gemini, and stores them in a local vector
database (`vectra`) — then retrieves the most relevant chunks at generation
time to ground each LinkedIn post in your actual writing, projects, and notes.

## How it fits together

```
documents/               your real files — drop anything in here
   │
   ▼
ingest.js                reads, chunks, embeds, stores in vector-index/
   │  (or watch-ingest.js runs this automatically on file changes)
   ▼
vector-index/             the local vector database (files on disk)
   │
   ▼
agent-core.js             retrieves top-k relevant chunks for a topic,
                           feeds them to Gemini to draft the post,
                           optionally generates an image, publishes to LinkedIn
   │
   ▼
server.js                 Telegram bot + internal cron schedule that calls
                           agent-core.js on command or on schedule
```

## Files in this project

| File | Purpose |
|---|---|
| `documents/` | **Put your real files here** — notes, past posts, resume, project write-ups |
| `chunker.js` | Splits document text into overlapping ~800-character chunks |
| `file-readers.js` | Extracts text from `.txt`, `.md`, `.pdf`, `.docx` |
| `vector-store.js` | Wraps the local vector database (vectra) and Gemini embedding calls |
| `ingest.js` | Scans `documents/`, embeds new/changed files, updates the vector DB, removes deleted files' vectors |
| `watch-ingest.js` | Watches `documents/` and auto re-runs ingestion the moment a file changes |
| `ingest-manifest.json` | Auto-generated — tracks which files are already indexed, so unchanged files aren't re-embedded |
| `vector-index/` | Auto-generated — the actual vector database files |
| `agent-core.js` | Retrieval + generation + LinkedIn posting logic |
| `server.js` | Telegram webhook + scheduled auto-posting |
| `topics.json`, `state.json` | Your rotating topic list for scheduled posts |

## Why this design is efficient

- **Incremental ingestion**: `ingest.js` hashes each file's content. Unchanged
  files are skipped entirely — adding one new file to a folder of 100 only
  costs embedding calls for that one file, not all 100.
- **Local vector database**: `vectra` stores everything as files on disk, no
  external database service, no network calls except to Gemini for
  embeddings. Retrieval (cosine similarity search) happens locally and is
  effectively instant for a personal-scale document set.
- **Automatic updates**: `watch-ingest.js` means you never manually re-run
  anything — save a file in `documents/`, and within a couple seconds it's
  chunked, embedded, and searchable.

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Add your environment variables

Create a `.env` file (or export these in your shell) — do **not** commit this file:

```
GEMINI_API_KEY=your_gemini_key
LINKEDIN_ACCESS_TOKEN=your_linkedin_token
LINKEDIN_PERSON_URN=urn:li:person:your_id
TELEGRAM_BOT_TOKEN=your_new_bot_token
TELEGRAM_OWNER_ID=your_telegram_numeric_id
```

If running locally, load it with a small addition at the top of `server.js`
and `ingest.js`:
```bash
npm install dotenv
```
then add `require("dotenv").config();` as the very first line of each file
that reads `process.env`.

### 3. Add your documents

Drop real files into `documents/` — your resume, past LinkedIn posts, project
write-ups, blog drafts, anything that reflects how you actually write and
what you've actually done. Subfolders are fine too.

### 4. Run the first ingestion

```bash
npm run ingest
```

You'll see console output per file: new, changed, or skipped, and how many
chunks were created. This builds `vector-index/` for the first time.

### 5. Start the auto-watcher (recommended)

In a separate terminal:
```bash
npm run watch
```
Leave this running while you work. Any time you add or edit a file in
`documents/`, it re-indexes automatically within a couple seconds.

### 6. Run the agent server

```bash
npm start
```

## Running this for real: two options

### Option A — Run it locally (matches "reads from my laptop automatically")

Since your documents live on your laptop, running the server locally means
retrieval always reflects your latest files with zero sync step. To let
Telegram reach a server on your own machine, use a tunnel:

```bash
npm install -g localtunnel
lt --port 3000
```
(or use [ngrok](https://ngrok.com) similarly)

This gives you a temporary public URL. Register it as your Telegram webhook:
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<tunnel-url>/telegram-webhook
```

**Trade-off**: the bot only works while your laptop is on, awake, and the
tunnel is running. Fine for personal/dev use; not fine if you want posts to
go out while your laptop is closed.

### Option B — Deploy to the cloud (Render/Railway), sync documents via git

Deploy exactly as described in the earlier setup guide. The difference: your
`documents/` folder and `vector-index/` need to be committed and pushed
whenever you add new content, since the cloud server only sees what's in the
repo:

```bash
npm run ingest
git add documents/ vector-index/ ingest-manifest.json
git commit -m "Add new documents"
git push
```

Render redeploys automatically on push, picking up the updated index.

**Trade-off**: not truly "automatic" — there's a manual push step — but the
bot works 24/7 regardless of your laptop's state.

**If you want true automatic + always-on**, the real fix is syncing your
documents folder to cloud storage the agent can read directly (e.g. a
Google Drive folder your server polls) instead of local files — that's a
bigger change; say so if you want it built out.

## A note on quality

RAG only helps if `documents/` actually has substance in it. A folder with
one thin bio file will barely change the output. The more real writing,
project details, and opinions you feed it, the less generic each post will
sound — this is the single biggest lever on quality in this whole system.
