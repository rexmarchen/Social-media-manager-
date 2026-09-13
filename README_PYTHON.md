# 🚀 LinkedIn Auto-Repurposing & Posting Agent

Convert **YouTube videos**, **web articles**, or **topics** directly into high-impact LinkedIn posts using AI (Gemini, Claude, or ChatGPT) and publish via LinkedIn's official Posts API.

You **don't need to write articles or prepare notes** manually:
- Paste a **YouTube link** → The agent fetches the video transcript automatically (no API key required), extracts key takeaways, and drafts a structured LinkedIn post.
- Paste an **article or blog link** → The agent scrapes the text, summarizes core insights, and generates an authentic post.
- Or type any **topic / idea** (or press Enter to rotate from `topics.json`).

---

## 🛠️ Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Your `.env` file is already pre-configured with:
   - `GEMINI_API_KEY` (ready to use immediately!)
   - `LINKEDIN_ACCESS_TOKEN` & `LINKEDIN_PERSON_URN`
   - Optional: Add `ANTHROPIC_API_KEY` (for Claude) or `OPENAI_API_KEY` (for ChatGPT).

---

## 🎯 How to Run

### 1. Interactive Mode (Easiest)
Just run the script with no arguments. It will prompt you to paste a YouTube link, article URL, or topic:
```bash
python linkedin_agent.py
```
It shows you a live preview and asks for confirmation (`y/n`) before publishing to LinkedIn!

### 2. Repurpose a YouTube Video
Pass any YouTube video (podcasts, tutorials, tech talks, interviews):
```bash
# Preview draft only (no posting)
python linkedin_agent.py --youtube "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" --dry-run

# Generate and publish live
python linkedin_agent.py --youtube "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

### 3. Repurpose an Article or Blog
```bash
python linkedin_agent.py --url "https://techcrunch.com/article..." --dry-run
```

### 4. Generate from a Quick Topic or Idea
```bash
python linkedin_agent.py --topic "Why backend developers should understand cache invalidation" --dry-run
```

### 5. Automated Daily Scheduling
```bash
python linkedin_agent.py --schedule
```
Runs continuously and posts daily at `POST_TIME` using rotating topics from `topics.json`.


## Things that WILL break this if you ignore them

- **Token expiry**: LinkedIn access tokens expire after 60 days. You'll need
  to implement the OAuth refresh flow (or manually regenerate) before then,
  or the script starts failing with 401s.
- **Rate limits**: LinkedIn caps posting API calls at roughly 100/day per
  member. One post a day is nowhere close to that, but don't loop this
  aggressively for testing.
- **API version header**: The `LINKEDIN_VERSION` constant in the script
  needs bumping periodically — LinkedIn versions this API monthly
  (e.g. `202601`). Check LinkedIn's developer docs if you start getting
  version-related errors.
- **Content quality**: an unattended agent posting daily can drift into
  repetitive or generic content over weeks. Consider logging every post to
  a file/database so you can review a week's worth at a glance, and maybe
  add a human-approval step (post to a Slack DM or email for a thumbs up
  before it goes live) rather than fully blind auto-publish, at least at first.

## Extending it

- **Multiple topics**: rotate `POST_TOPIC` from a list or file instead of a single value.
- **Images**: the Posts API supports image attachments, but it's a two-step
  upload process (register the asset, upload the binary, then reference the
  returned URN in the post payload) — ask if you want this added.
- **Human-in-the-loop**: instead of `lifecycleState: PUBLISHED`, you could
  save the draft somewhere (email yourself, or a simple web dashboard) and
  only publish after you approve it — safer for a brand-new automation.
