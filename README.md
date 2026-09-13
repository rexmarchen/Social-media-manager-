# 🚀 LinkedIn RAG Agent (Powered by Gemini)

An automated agent that retrieves authentic context about your background, projects, and opinions using lightweight in-memory RAG, drafts engaging LinkedIn posts using Google Gemini, evaluates whether an image is beneficial, and publishes directly to LinkedIn.

Runs autonomously on a schedule via **GitHub Actions** — with **zero server infrastructure costs**.

> 💡 **Looking for the Python (Claude) version?** See [README_PYTHON.md](file:///c:/Users/anshupal/OneDrive/Documents/linkdin%20automation/README_PYTHON.md) and [linkedin_agent.py](file:///c:/Users/anshupal/OneDrive/Documents/linkdin%20automation/linkedin_agent.py).

---


## 🏗️ Architecture

```text
┌─────────────────────────┐
│   GitHub Actions cron   │  (Runs daily or on-demand)
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 1. Load Knowledge Base  │  (Reads knowledge.json: bio, past posts, projects)
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 2. In-Memory RAG        │  (Embeds topic + knowledge chunks, ranks by cosine similarity)
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 3. Gemini Post Draft    │  (Grounded post generation + image necessity check)
└────────────┬─────────────┘
             │
    Image needed?
    ┌────────┴────────┐
   Yes                No
    │                 │
    ▼                 │
┌──────────────────┐  │
│ 4. Gemini Image  │  │  (Generates supporting illustration)
└──────────┬───────┘  │
           │          │
           ▼          ▼
┌─────────────────────────┐
│ 5. LinkedIn Image Upload│  (Two-step upload: register -> binary PUT)
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 6. LinkedIn Publish     │  (Publishes via LinkedIn REST API)
└────────────┬─────────────┘
             │
             ▼
┌─────────────────────────┐
│ 7. Commit Updated State │  (Updates state.json in repo)
└─────────────────────────┘
```

---

## 📁 Repository Structure

- `agent.js` — Core agent logic (RAG retrieval, Gemini post generation, image handling, LinkedIn upload and publish).
- `test-dry-run.js` — Safe local testing script that retrieves context and drafts posts without touching LinkedIn.
- `knowledge.json` — Your personal knowledge chunks (achievements, projects, learnings, opinions).
- `topics.json` — Curated rotating queue of discussion topics.
- `state.json` — Pointer recording the last posted topic index.
- `.github/workflows/linkedin-rag-agent.yml` — GitHub Actions workflow for scheduled execution.
- `.env.example` — Environment variable template for local execution.

---

## ⚙️ Prerequisites & Setup

### 1. Get Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** and generate a new key.
3. Keep this handy for `GEMINI_API_KEY`.

### 2. Get LinkedIn OAuth Access Token & Person URN
1. Create an application on the [LinkedIn Developer Portal](https://www.linkedin.com/developers/).
2. Under the **Auth** tab, request the `w_member_social` and `openid`, `profile`, `email` scopes.
3. Generate an access token via OAuth 2.0 (or via the Developer Portal's Token Generator tool) with `w_member_social` permission.
4. To find your **Person URN**:
   Make a GET request using your access token:
   ```bash
   curl -X GET "https://api.linkedin.com/v2/userinfo" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
   ```
   Find the `"sub"` field in the JSON response (e.g. `"AbC123xyz"`). Your `LINKEDIN_PERSON_URN` is:
   ```text
   urn:li:person:AbC123xyz
   ```

---

## 🧪 Local Development & Testing

1. Install dependencies:
   ```bash
   npm install
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
   Fill in your `GEMINI_API_KEY`, `LINKEDIN_ACCESS_TOKEN`, and `LINKEDIN_PERSON_URN`.

3. **Run a Dry Run** (no LinkedIn post created):
   ```bash
   npm run dry-run
   ```
   *If `GEMINI_API_KEY` is not set yet, it will output a simulated dry-run.*

4. **Run the Full Agent Locally**:
   ```bash
   npm start
   ```

---

## 🤖 GitHub Actions Setup (Automated Deployment)

1. Push this repository to GitHub.
2. In your GitHub repository, go to **Settings** → **Secrets and variables** → **Actions**.
3. Under **Repository secrets**, add:
   - `GEMINI_API_KEY`: Your Gemini API Key.
   - `LINKEDIN_ACCESS_TOKEN`: Your LinkedIn OAuth token.
   - `LINKEDIN_PERSON_URN`: Your `urn:li:person:...` identifier.
4. Verify Workflow Permissions:
   - Go to **Settings** → **Actions** → **General** → **Workflow permissions**.
   - Select **Read and write permissions** (required so the bot can commit `state.json` back to the repository).
5. Trigger manually:
   - Navigate to the **Actions** tab.
   - Click on **LinkedIn RAG Agent** in the left sidebar.
   - Click **Run workflow**.

---

## 🧠 Customizing the Agent

### Personalize `knowledge.json`
Add your real achievements, tools, and background into `knowledge.json`. The richer your chunks, the more authentic your posts:
```json
[
  {
    "id": "project-distributed-cache",
    "text": "Built a custom raft consensus module in Go to understand distributed systems. Spent two weeks debugging network partition edge cases."
  }
]
```

### Adjust Rotating Topics in `topics.json`
Add questions or talking points that match your target audience or career direction.

### Model Configurations
You can switch Gemini models by setting environment variables in `.env` or in `agent.js`:
- `GEMINI_TEXT_MODEL` (default: `gemini-2.0-flash`)
- `GEMINI_EMBEDDING_MODEL` (default: `text-embedding-004`)
- `GEMINI_IMAGE_MODEL` (default: `imagen-3.0-generate-002`)
