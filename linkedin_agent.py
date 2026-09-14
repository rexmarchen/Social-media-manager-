"""
LinkedIn Auto-Posting & Repurposing Agent
-----------------------------------------
Automatically converts raw inputs into high-engagement LinkedIn posts:
  - YouTube videos (fetches transcript automatically)
  - Articles & web pages (extracts core text)
  - Raw topics or notes
  - Rotating topics from topics.json

Supported AI Engines:
  - Google Gemini (gemini-3.8-flash / gemini-3.6-flash) - Ready by default from .env
  - Anthropic Claude (claude-3-7-sonnet-latest)
  - OpenAI ChatGPT (gpt-4o / gpt-4o-mini)

Run modes:
  python linkedin_agent.py                     -> Interactive mode (paste a YouTube link or topic)
  python linkedin_agent.py --youtube <URL>     -> Repurpose a YouTube video
  python linkedin_agent.py --url <URL>         -> Repurpose any article or web page
  python linkedin_agent.py --topic "<topic>"   -> Write a post on a specific topic
  python linkedin_agent.py --dry-run           -> Generate draft without publishing to LinkedIn
  python linkedin_agent.py --once              -> Generate + post immediately to LinkedIn
  python linkedin_agent.py --schedule          -> Autonomous daily posting at POST_TIME
"""

import os
import re
import sys
import json
import logging
import requests
from dotenv import load_dotenv

# Ensure Windows terminal handles emojis and UTF-8 cleanly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


# Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_URN = os.environ.get("LINKEDIN_PERSON_URN")
LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION", "202603")
API_BASE = "https://api.linkedin.com"

POST_TOPIC = os.environ.get("POST_TOPIC", "Latest breakthroughs in Applied AI & Distributed Systems")
POST_TIME = os.environ.get("POST_TIME", "09:00")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("linkedin_agent")


# =====================================================================
# 1. Content Extractors (YouTube, Web Articles, Topics)
# =====================================================================

def extract_youtube_id(url: str) -> str:
    """Extract 11-character video ID from any YouTube URL format."""
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]
    for pattern in patterns:
        m = re.search(pattern, url.strip())
        if m:
            return m.group(1)
    return url.strip()


def fetch_youtube_transcript(video_url_or_id: str) -> str:
    """Fetch transcript text from YouTube video without needing a Google API key."""
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = extract_youtube_id(video_url_or_id)
    log.info("Fetching YouTube transcript for video ID: %s", video_id)
    try:
        ytt = YouTubeTranscriptApi()
        items = ytt.fetch(video_id)
        snippets = []
        for item in items:
            if hasattr(item, "text"):
                snippets.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                snippets.append(item["text"])
        transcript = " ".join(snippets)
        if not transcript.strip():
            raise ValueError("Transcript was empty.")
        log.info("Successfully fetched %d words of transcript from YouTube.", len(transcript.split()))
        return transcript[:12000]  # Keep first ~12k characters for LLM context window
    except Exception as e:
        log.error("Failed to retrieve transcript: %s", e)
        raise RuntimeError(f"Could not extract transcript for YouTube video ({e}). Ensure subtitles/captions are available on this video.")


def fetch_article_text(url: str) -> str:
    """Scrape article body text from any webpage."""
    from bs4 import BeautifulSoup

    log.info("Scraping content from URL: %s", url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "li"])]
    clean_text = "\n".join([p for p in paragraphs if len(p) > 25])
    if not clean_text.strip():
        clean_text = soup.get_text(" ", strip=True)

    log.info("Extracted %d characters of text from article.", len(clean_text))
    return clean_text[:12000]


def get_rotating_topic() -> str:
    """Read next topic from topics.json if available, otherwise fall back to POST_TOPIC."""
    topics_file = "topics.json"
    state_file = "state.json"
    if os.path.exists(topics_file):
        try:
            with open(topics_file, "r", encoding="utf-8") as f:
                topics = json.load(f)
            if topics:
                last_idx = -1
                if os.path.exists(state_file):
                    try:
                        with open(state_file, "r", encoding="utf-8") as f:
                            last_idx = json.load(f).get("lastIndex", -1)
                    except Exception:
                        pass
                next_idx = (last_idx + 1) % len(topics)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"lastIndex": next_idx}, f, indent=2)
                log.info("Selected topic #%d from topics.json", next_idx + 1)
                return topics[next_idx]
        except Exception as e:
            log.warning("Could not read topics.json: %s. Using POST_TOPIC fallback.", e)
    return POST_TOPIC


# =====================================================================
# 2. AI Post Generation (Gemini / Claude / ChatGPT)
# =====================================================================

def build_prompt(source_type: str, raw_content: str) -> str:
    return f"""You are a top-tier LinkedIn creator and tech professional.
Transform the following {source_type} into a compelling, authentic, high-engagement LinkedIn post.

RAW CONTENT / INPUT:
\"\"\"
{raw_content}
\"\"\"

POST STRUCTURE & RULES:
1. Hook (First 1-2 lines): An attention-grabbing hook that stops the scroll. Make it thought-provoking or counterintuitive. Do NOT use generic openings like "Excited to share" or "I recently watched".
2. Context & Core Insights (120-180 words):
   - Summarize the 3 to 4 most valuable takeaways or practical lessons.
   - Use clean, easily scannable bullet points or short paragraphs.
   - Explain *why* it matters, not just what was said.
3. Personal Perspective: Add a brief, grounded insight or actionable recommendation for engineers, founders, or professionals.
4. Closing: An open-ended question that naturally invites people to join the discussion (avoid lazy cliches like "Thoughts?").
5. Hashtags: Exactly 3 relevant hashtags at the bottom.
6. Tone: Human, authentic, insightful, humble yet authoritative. Avoid corporate jargon, buzzwords, and emoji overload.

Return ONLY the final LinkedIn post text, nothing else (no preambles, notes, or quotation marks)."""


def generate_post_with_gemini(prompt: str) -> str:
    candidate_models = [
        os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.6-flash"),
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]

    # Remove duplicates while preserving order
    seen = set()
    models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    last_error = None
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model_name in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                log.warning("Gemini model %s returned status %d. Trying next candidate...", model_name, resp.status_code)
                last_error = f"Status {resp.status_code}: {resp.text}"
        except Exception as e:
            log.warning("Gemini model %s failed (%s). Trying next candidate...", model_name, e)
            last_error = str(e)

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")



def generate_post_with_claude(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    model = os.environ.get("ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
    response = client.messages.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def generate_post_with_openai(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_post(source_type: str, raw_content: str) -> str:
    """Route post generation to available AI engine."""
    prompt = build_prompt(source_type, raw_content)

    # Determine which provider to use
    if LLM_PROVIDER == "gemini" or (not LLM_PROVIDER and GEMINI_API_KEY):
        log.info("Generating post with Google Gemini...")
        return generate_post_with_gemini(prompt)
    elif LLM_PROVIDER == "claude" or (not LLM_PROVIDER and ANTHROPIC_API_KEY):
        log.info("Generating post with Anthropic Claude...")
        return generate_post_with_claude(prompt)
    elif LLM_PROVIDER == "openai" or (not LLM_PROVIDER and OPENAI_API_KEY):
        log.info("Generating post with OpenAI ChatGPT...")
        return generate_post_with_openai(prompt)
    else:
        raise ValueError(
            "No AI API key found. Please set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY in your .env file."
        )


# =====================================================================
# 3. LinkedIn Publishing API
# =====================================================================

def get_person_urn() -> str:
    """Fetch or return the authenticated user's LinkedIn URN."""
    if LINKEDIN_PERSON_URN and LINKEDIN_PERSON_URN.startswith("urn:li:person:"):
        return LINKEDIN_PERSON_URN

    if not LINKEDIN_ACCESS_TOKEN:
        raise ValueError("LINKEDIN_ACCESS_TOKEN is missing from .env.")

    resp = requests.get(
        f"{API_BASE}/v2/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=15,
    )
    resp.raise_for_status()
    sub = resp.json().get("sub")
    return f"urn:li:person:{sub}"


def publish_post(text: str, author_urn: str) -> str:
    """Publish text commentary to LinkedIn via the official REST API."""
    if not LINKEDIN_ACCESS_TOKEN:
        raise ValueError("LINKEDIN_ACCESS_TOKEN is missing from .env.")

    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    resp = requests.post(
        f"{API_BASE}/rest/posts",
        headers={
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": LINKEDIN_VERSION,
        },
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.headers.get("x-restli-id", "published")


# =====================================================================
# 4. Pipeline Execution & Workflows
# =====================================================================

def process_and_post(source_type: str, raw_content: str, dry_run: bool = False):
    """Full workflow: generate post -> preview -> optionally publish."""
    print("\n" + "=" * 60)
    print(f"🤖 [Agent] Processing {source_type.upper()}...")
    print("=" * 60)

    post_text = generate_post(source_type, raw_content)

    print("\n" + "-" * 25 + " GENERATED POST " + "-" * 25)
    print(post_text)
    print("-" * 66 + "\n")

    if dry_run:
        log.info("Dry-run active. Post was NOT sent to LinkedIn.")
        return post_text

    try:
        author_urn = get_person_urn()
        log.info("Publishing to LinkedIn as %s...", author_urn)
        post_id = publish_post(post_text, author_urn)
        log.info("🚀 Posted successfully to LinkedIn! Post ID: %s", post_id)
        return post_text
    except Exception as e:
        log.error("Failed to publish to LinkedIn: %s", e)
        raise


def interactive_mode():
    """Friendly interactive CLI prompt."""
    print("=" * 65)
    print("🚀 LinkedIn Auto-Repurposing Agent")
    print("=" * 65)
    print("Easily convert any input into a ready-to-publish LinkedIn post.")
    print("Supported inputs:")
    print("  [1] YouTube Video Link (e.g. https://www.youtube.com/watch?v=...)")
    print("  [2] Web Article / Blog URL (e.g. https://example.com/blog/...)")
    print("  [3] Topic or Idea (e.g. 'How Redis caching prevents database bottlenecks')")
    print("  [4] Press [Enter] to pull next topic from topics.json")
    print("-" * 65)

    user_input = input("Enter link or topic: ").strip()

    if not user_input:
        topic = get_rotating_topic()
        source_type = "Rotating Topic"
        content = topic
    elif "youtube.com" in user_input or "youtu.be" in user_input:
        source_type = "YouTube Video Transcript"
        content = fetch_youtube_transcript(user_input)
    elif user_input.startswith("http://") or user_input.startswith("https://"):
        source_type = "Web Article"
        content = fetch_article_text(user_input)
    else:
        source_type = "Topic Prompt"
        content = user_input

    # Preview first
    post_text = process_and_post(source_type, content, dry_run=True)

    # Ask for confirmation before posting live
    confirm = input("Would you like to publish this to your LinkedIn now? (y/n): ").strip().lower()
    if confirm in ["y", "yes"]:
        author_urn = get_person_urn()
        post_id = publish_post(post_text, author_urn)
        log.info("🚀 Published live to LinkedIn! Post ID: %s", post_id)
    else:
        print("Canceled. Post was not published.")


def run_scheduled():
    """Run continuously, posting once a day at POST_TIME."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    try:
        hour, minute = map(int, POST_TIME.split(":"))
    except ValueError:
        log.error("Invalid POST_TIME format: '%s'. Expected 'HH:MM'.", POST_TIME)
        sys.exit(1)

    scheduler = BlockingScheduler()

    def scheduled_job():
        topic = get_rotating_topic()
        process_and_post("Daily Scheduled Topic", topic, dry_run=False)

    scheduler.add_job(scheduled_job, "cron", hour=hour, minute=minute)
    log.info("Scheduler started. Will post daily at %s (local time). Press Ctrl+C to stop.", POST_TIME)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


# =====================================================================
# Main CLI Entry Point
# =====================================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    dry_run = "--dry-run" in args

    if "--youtube" in args:
        idx = args.index("--youtube")
        if idx + 1 < len(args):
            url = args[idx + 1]
            transcript = fetch_youtube_transcript(url)
            process_and_post("YouTube Video", transcript, dry_run=dry_run)
        else:
            print("Error: Please provide a YouTube URL after --youtube")

    elif "--url" in args:
        idx = args.index("--url")
        if idx + 1 < len(args):
            url = args[idx + 1]
            article = fetch_article_text(url)
            process_and_post("Article", article, dry_run=dry_run)
        else:
            print("Error: Please provide a URL after --url")

    elif "--topic" in args:
        idx = args.index("--topic")
        if idx + 1 < len(args):
            topic = args[idx + 1]
            process_and_post("Topic", topic, dry_run=dry_run)
        else:
            print("Error: Please provide a topic after --topic")

    elif "--schedule" in args:
        run_scheduled()

    elif "--once" in args:
        topic = get_rotating_topic()
        process_and_post("Daily Topic", topic, dry_run=dry_run)

    else:
        # Default: Interactive mode
        interactive_mode()
