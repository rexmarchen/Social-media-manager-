"""
Social Media Manager Agent with RAG, approvals, and multi-platform posting.

Core workflow:
  1. Ingest approved local folders into ChromaDB.
  2. Retrieve relevant context for a topic, URL, or YouTube transcript.
  3. Draft platform-specific posts for LinkedIn, Instagram, and Reddit.
  4. Save the draft and ask for approval before publishing by default.
  5. Publish only to platforms with configured credentials.

Examples:
  python social_agent.py --ingest --sources knowledge_base
  python social_agent.py --once --topic "What I learned building backend systems"
  python social_agent.py --approve drafts/20260912-101500-backend-systems.json
  python social_agent.py --check-access --platforms linkedin,reddit,instagram
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "chroma_db"
KNOWLEDGE_DIR = ROOT / "knowledge_base"
DRAFTS_DIR = ROOT / "drafts"
GENERATED_IMAGES_DIR = ROOT / "generated_images"
COLLECTION_NAME = os.environ.get("RAG_COLLECTION_NAME", "social_agent_knowledge")

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "120"))
MAX_FILE_BYTES = int(os.environ.get("RAG_MAX_FILE_BYTES", str(2 * 1024 * 1024)))

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".yml",
    ".yaml",
}

EXCLUDED_NAMES = {
    ".git",
    ".env",
    ".env.local",
    ".env.production",
    "node_modules",
    "__pycache__",
    "chroma_db",
    "drafts",
    "generated_images",
}

LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION", "202604")
INSTAGRAM_GRAPH_VERSION = os.environ.get("INSTAGRAM_GRAPH_VERSION", "v24.0")
DEFAULT_PLATFORMS = os.environ.get("SOCIAL_PLATFORMS", "linkedin").split(",")
REQUIRE_APPROVAL = os.environ.get("SOCIAL_AGENT_REQUIRE_APPROVAL", "true").lower() != "false"
GENERATE_IMAGES = os.environ.get("SOCIAL_AGENT_GENERATE_IMAGES", "false").lower() == "true"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("social_agent")


@dataclass
class SourceContent:
    source_type: str
    text: str
    topic: str


def clean_platforms(value: str | list[str] | None) -> list[str]:
    if value is None:
        items = DEFAULT_PLATFORMS
    elif isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    platforms = [p.strip().lower() for p in items if p.strip()]
    allowed = {"linkedin", "instagram", "reddit"}
    bad = [p for p in platforms if p not in allowed]
    if bad:
        raise ValueError(f"Unsupported platform(s): {', '.join(bad)}. Use linkedin, instagram, reddit.")
    return platforms or ["linkedin"]


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "draft"


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts)


def read_text_file(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    if is_excluded(path):
        return None
    if path.stat().st_size > MAX_FILE_BYTES:
        log.warning("Skipping large file: %s", path)
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            log.warning("Skipping non-UTF text file: %s", path)
            return None


def iter_source_files(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        source = source.expanduser()
        if not source.is_absolute():
            source = ROOT / source
        if not source.exists():
            log.warning("Skipping missing source: %s", source)
            continue
        if source.is_file():
            if read_text_file(source) is not None:
                files.append(source)
            continue
        for path in source.rglob("*"):
            if path.is_file() and read_text_file(path) is not None:
                files.append(path)
    return sorted(set(files))


def get_chroma_collection(reset: bool = False):
    import chromadb

    client = chromadb.PersistentClient(path=str(DB_DIR))
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(name=COLLECTION_NAME)


def ingest_sources(sources: list[str], reset: bool = False) -> int:
    source_paths = [Path(s) for s in sources] if sources else [KNOWLEDGE_DIR]
    files = iter_source_files(source_paths)
    if not files:
        raise FileNotFoundError("No readable text files found in the approved source folders.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    ids: list[str] = []
    docs: list[str] = []
    metadatas: list[dict[str, str | int]] = []

    for path in files:
        text = read_text_file(path)
        if not text or not text.strip():
            continue
        rel_path = str(path.resolve().relative_to(ROOT)) if path.resolve().is_relative_to(ROOT) else str(path)
        for index, chunk in enumerate(splitter.split_text(text)):
            chunk = chunk.strip()
            if not chunk:
                continue
            digest = hashlib.sha1(f"{path.resolve()}:{index}:{chunk[:80]}".encode("utf-8")).hexdigest()
            ids.append(digest)
            docs.append(chunk)
            metadatas.append({"source": rel_path, "chunk": index})

    if not docs:
        raise ValueError("No chunks were created from the approved source folders.")

    collection = get_chroma_collection(reset=reset)
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    return len(docs)


def retrieve_context(query: str, top_k: int = 6) -> str:
    try:
        collection = get_chroma_collection()
        result = collection.query(query_texts=[query], n_results=top_k)
    except Exception as exc:
        log.warning("RAG retrieval failed: %s", exc)
        return ""

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    lines = []
    for doc, meta in zip(documents, metadatas):
        source = meta.get("source", "unknown") if isinstance(meta, dict) else "unknown"
        lines.append(f"Source: {source}\n{doc}")
    return "\n\n---\n\n".join(lines)


def extract_youtube_id(url: str) -> str:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return url.strip()


def fetch_youtube_transcript(video_url_or_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = extract_youtube_id(video_url_or_id)
    items = YouTubeTranscriptApi().fetch(video_id)
    snippets = []
    for item in items:
        if hasattr(item, "text"):
            snippets.append(item.text)
        elif isinstance(item, dict) and "text" in item:
            snippets.append(item["text"])
    text = " ".join(snippets).strip()
    if not text:
        raise RuntimeError("No transcript text was available for that YouTube video.")
    return text[:16000]


def fetch_article_text(url: str) -> str:
    from bs4 import BeautifulSoup

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 social-agent/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    parts = [p.get_text(" ", strip=True) for p in soup.find_all(["h1", "h2", "h3", "p", "li"])]
    text = "\n".join(p for p in parts if len(p) > 25).strip()
    return (text or soup.get_text(" ", strip=True))[:16000]


def get_rotating_topic() -> str:
    topics_path = ROOT / "topics.json"
    state_path = ROOT / "state.json"
    topics = json.loads(topics_path.read_text(encoding="utf-8")) if topics_path.exists() else []
    if not topics:
        return os.environ.get("POST_TOPIC", "What I learned recently while building software")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"lastIndex": -1}
    next_index = (int(state.get("lastIndex", -1)) + 1) % len(topics)
    state_path.write_text(json.dumps({"lastIndex": next_index}, indent=2), encoding="utf-8")
    return topics[next_index]


def resolve_source_content(args: argparse.Namespace) -> SourceContent:
    if args.youtube:
        text = fetch_youtube_transcript(args.youtube)
        return SourceContent("youtube", text, args.topic or f"Lessons from YouTube video {extract_youtube_id(args.youtube)}")
    if args.url:
        text = fetch_article_text(args.url)
        return SourceContent("article", text, args.topic or args.url)
    if args.topic:
        return SourceContent("topic", args.topic, args.topic)
    topic = get_rotating_topic()
    return SourceContent("topic", topic, topic)


def build_generation_prompt(content: SourceContent, context: str, platforms: list[str]) -> str:
    platform_rules = {
        "linkedin": "Professional, personal, 120-190 words, strong first line, 3-5 specific hashtags.",
        "instagram": "Warm caption, shorter lines, optional tasteful emojis, 5-8 hashtags, no fake claims.",
        "reddit": "Subreddit-native, useful title, conversational selftext, no marketing tone, no hashtags.",
    }
    selected_rules = "\n".join(f"- {p}: {platform_rules[p]}" for p in platforms)

    return f"""You are a careful social media manager for one person, not a spam bot.
Create platform-specific drafts from the input and local RAG context.

TOPIC:
{content.topic}

INPUT TYPE:
{content.source_type}

RAW INPUT:
\"\"\"
{content.text[:12000]}
\"\"\"

RAG CONTEXT FROM THE USER'S APPROVED LOCAL FILES:
\"\"\"
{context or "No relevant context found."}
\"\"\"

PLATFORMS AND STYLE RULES:
{selected_rules}

Safety and quality rules:
- Use only details supported by the raw input or RAG context.
- Do not claim the user did work they did not do.
- Do not include secrets, file paths, private tokens, or anything that looks like a credential.
- Keep the voice human, practical, and specific.
- If an image would help, suggest a simple professional graphic/photo idea.

Return ONLY valid JSON in this shape:
{{
  "linkedin": {{"text": "draft or empty string"}},
  "instagram": {{"caption": "draft or empty string"}},
  "reddit": {{"title": "draft or empty string", "selftext": "draft or empty string", "subreddit": "configured subreddit or empty string"}},
  "image": {{"needed": true, "prompt": "image prompt or empty string"}}
}}"""


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError(f"Model did not return JSON: {text[:500]}")
    return json.loads(match.group(0))


def generate_with_gemini(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing.")
    model = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 2500},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    return extract_json(raw_text)


def generate_with_openai(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing.")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    return extract_json(response.json()["choices"][0]["message"]["content"])


def generate_with_claude(prompt: str) -> dict[str, Any]:
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is missing.")
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-3-7-sonnet-latest"),
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json(response.content[0].text)


def generate_fallback(content: SourceContent, platforms: list[str]) -> dict[str, Any]:
    base = (
        f"{content.topic}\n\n"
        "One thing I keep noticing: the useful lessons usually come from building, measuring, "
        "and then tightening the feedback loop.\n\n"
        "The part worth sharing is not just the final result, but what changed in the way I think "
        "about the problem. That is where the real learning compounds.\n\n"
        "What is one lesson you only understood after implementing it yourself?"
    )
    return {
        "linkedin": {"text": base + "\n\n#SoftwareEngineering #AI #LearningInPublic"},
        "instagram": {"caption": base + "\n\n#softwareengineering #buildinpublic #ai #coding #learning"},
        "reddit": {
            "title": content.topic[:280],
            "selftext": base,
            "subreddit": os.environ.get("REDDIT_SUBREDDIT", ""),
        },
        "image": {"needed": False, "prompt": ""},
    }


def generate_posts(content: SourceContent, context: str, platforms: list[str]) -> dict[str, Any]:
    prompt = build_generation_prompt(content, context, platforms)
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    try:
        if provider == "openai":
            return generate_with_openai(prompt)
        if provider == "claude":
            return generate_with_claude(prompt)
        if provider == "gemini" or os.environ.get("GEMINI_API_KEY"):
            return generate_with_gemini(prompt)
        if os.environ.get("OPENAI_API_KEY"):
            return generate_with_openai(prompt)
        if os.environ.get("ANTHROPIC_API_KEY"):
            return generate_with_claude(prompt)
    except Exception as exc:
        log.warning("AI generation failed, using local fallback draft: %s", exc)
    return generate_fallback(content, platforms)


def generate_image_with_gemini(prompt: str) -> Path | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not prompt:
        return None
    model = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
    is_imagen = model.startswith("imagen")
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"
        if is_imagen
        else f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    body = (
        {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "1:1", "outputOptions": {"mimeType": "image/jpeg"}},
        }
        if is_imagen
        else {"contents": [{"parts": [{"text": prompt}]}]}
    )
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json=body,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    image_b64 = data.get("predictions", [{}])[0].get("bytesBase64Encoded")
    if not image_b64:
        for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if part.get("inlineData", {}).get("data"):
                image_b64 = part["inlineData"]["data"]
                break
    if not image_b64:
        return None

    import base64

    GENERATED_IMAGES_DIR.mkdir(exist_ok=True)
    path = GENERATED_IMAGES_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.jpg"
    path.write_bytes(base64.b64decode(image_b64))
    return path


def save_draft(content: SourceContent, platforms: list[str], posts: dict[str, Any], context: str, image_path: str | None, image_url: str | None) -> Path:
    DRAFTS_DIR.mkdir(exist_ok=True)
    draft_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe_slug(content.topic)}"
    draft = {
        "id": draft_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "draft",
        "topic": content.topic,
        "source_type": content.source_type,
        "platforms": platforms,
        "posts": posts,
        "image": {
            "local_path": image_path,
            "public_url": image_url,
            "prompt": posts.get("image", {}).get("prompt", ""),
            "needed": posts.get("image", {}).get("needed", False),
        },
        "rag_context_preview": context[:3000],
        "publish_results": {},
    }
    draft_path = DRAFTS_DIR / f"{draft_id}.json"
    draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return draft_path


def print_draft_preview(draft_path: Path) -> None:
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    print(f"\nDraft saved: {draft_path}")
    for platform in draft["platforms"]:
        print("\n" + "=" * 72)
        print(platform.upper())
        print("=" * 72)
        post = draft["posts"].get(platform, {})
        if platform == "linkedin":
            print(post.get("text", ""))
        elif platform == "instagram":
            print(post.get("caption", ""))
        elif platform == "reddit":
            print(f"Title: {post.get('title', '')}\n")
            print(post.get("selftext", ""))
            if post.get("subreddit"):
                print(f"\nSubreddit: r/{post.get('subreddit')}")
    image = draft.get("image", {})
    if image.get("local_path") or image.get("public_url") or image.get("needed"):
        print("\n" + "=" * 72)
        print("IMAGE")
        print("=" * 72)
        print(f"Local path: {image.get('local_path') or '(none)'}")
        print(f"Public URL: {image.get('public_url') or '(none)'}")
        print(f"Prompt: {image.get('prompt') or '(none)'}")


def linkedin_headers() -> dict[str, str]:
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN is missing.")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": LINKEDIN_VERSION,
    }


def get_linkedin_author() -> str:
    urn = os.environ.get("LINKEDIN_PERSON_URN")
    if urn and urn.startswith("urn:li:person:"):
        return urn
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN or LINKEDIN_PERSON_URN is required.")
    response = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    response.raise_for_status()
    return f"urn:li:person:{response.json()['sub']}"


def upload_linkedin_image(image_path: str, author: str) -> str:
    init = requests.post(
        "https://api.linkedin.com/rest/images?action=initializeUpload",
        headers=linkedin_headers(),
        json={"initializeUploadRequest": {"owner": author}},
        timeout=30,
    )
    init.raise_for_status()
    data = init.json()["value"]
    upload_url = data["uploadUrl"]
    image_urn = data["image"]
    with open(image_path, "rb") as handle:
        upload = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN']}", "Content-Type": "image/jpeg"},
            data=handle,
            timeout=60,
        )
    upload.raise_for_status()
    return image_urn


def publish_linkedin(text: str, image_path: str | None) -> str:
    author = get_linkedin_author()
    image_urn = upload_linkedin_image(image_path, author) if image_path else None
    payload: dict[str, Any] = {
        "author": author,
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
    if image_urn:
        payload["content"] = {"media": {"id": image_urn}}
    response = requests.post(
        "https://api.linkedin.com/rest/posts",
        headers=linkedin_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.headers.get("x-restli-id", "published")


def publish_instagram(caption: str, public_image_url: str | None) -> str:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not token or not ig_user_id:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID are required.")
    if not public_image_url:
        raise ValueError("Instagram feed publishing requires a public image URL. Set --image-url or INSTAGRAM_DEFAULT_IMAGE_URL.")
    base = f"https://graph.facebook.com/{INSTAGRAM_GRAPH_VERSION}/{ig_user_id}"
    create = requests.post(
        f"{base}/media",
        data={"image_url": public_image_url, "caption": caption, "access_token": token},
        timeout=30,
    )
    create.raise_for_status()
    creation_id = create.json()["id"]
    publish = requests.post(
        f"{base}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    publish.raise_for_status()
    return publish.json().get("id", "published")


def publish_reddit(title: str, selftext: str, subreddit_name: str, image_path: str | None) -> str:
    if not subreddit_name:
        subreddit_name = os.environ.get("REDDIT_SUBREDDIT", "")
    if not subreddit_name:
        raise ValueError("Reddit subreddit is missing. Set REDDIT_SUBREDDIT or put it in the draft.")

    import praw

    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID"),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
        username=os.environ.get("REDDIT_USERNAME"),
        password=os.environ.get("REDDIT_PASSWORD"),
        user_agent=os.environ.get("REDDIT_USER_AGENT", "social-agent/1.0 by local-user"),
    )
    subreddit = reddit.subreddit(subreddit_name)
    if image_path:
        try:
            from praw.models import PostMedia

            submission = subreddit.submit(title[:300], selftext=selftext, image=PostMedia(image_path))
        except Exception:
            submission = subreddit.submit_image(title[:300], image_path)
    else:
        submission = subreddit.submit(title[:300], selftext=selftext)
    return f"https://reddit.com{submission.permalink}" if submission else "published"


def check_access(platforms: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for platform in platforms:
        try:
            if platform == "linkedin":
                author = get_linkedin_author()
                results[platform] = f"ok ({author})"
            elif platform == "instagram":
                token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
                ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
                if not token or not ig_user_id:
                    raise ValueError("missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID")
                response = requests.get(
                    f"https://graph.facebook.com/{INSTAGRAM_GRAPH_VERSION}/{ig_user_id}",
                    params={"fields": "username", "access_token": token},
                    timeout=20,
                )
                response.raise_for_status()
                results[platform] = f"ok (@{response.json().get('username', ig_user_id)})"
            elif platform == "reddit":
                import praw

                reddit = praw.Reddit(
                    client_id=os.environ.get("REDDIT_CLIENT_ID"),
                    client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
                    username=os.environ.get("REDDIT_USERNAME"),
                    password=os.environ.get("REDDIT_PASSWORD"),
                    user_agent=os.environ.get("REDDIT_USER_AGENT", "social-agent/1.0 by local-user"),
                )
                results[platform] = f"ok (u/{reddit.user.me()})"
        except Exception as exc:
            results[platform] = f"failed ({exc})"
    return results


def publish_draft(draft_path: Path, dry_run: bool = False) -> dict[str, str]:
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    image = draft.get("image", {})
    local_image = image.get("local_path")
    public_image_url = image.get("public_url") or os.environ.get("INSTAGRAM_DEFAULT_IMAGE_URL")
    results: dict[str, str] = {}

    for platform in draft.get("platforms", []):
        post = draft.get("posts", {}).get(platform, {})
        if dry_run:
            results[platform] = "dry-run"
            continue
        if platform == "linkedin":
            results[platform] = publish_linkedin(post.get("text", ""), local_image)
        elif platform == "instagram":
            results[platform] = publish_instagram(post.get("caption", ""), public_image_url)
        elif platform == "reddit":
            results[platform] = publish_reddit(
                post.get("title", draft.get("topic", "")),
                post.get("selftext", ""),
                post.get("subreddit", ""),
                local_image,
            )

    draft["status"] = "published" if not dry_run else "dry-run"
    draft["publish_results"] = results
    draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def create_draft(args: argparse.Namespace) -> Path:
    platforms = clean_platforms(args.platforms)
    content = resolve_source_content(args)
    context = retrieve_context(content.topic, top_k=args.top_k)
    posts = generate_posts(content, context, platforms)

    image_path = args.image
    image_url = args.image_url or os.environ.get("INSTAGRAM_DEFAULT_IMAGE_URL")
    image_spec = posts.get("image", {})
    if not image_path and GENERATE_IMAGES and image_spec.get("needed") and image_spec.get("prompt"):
        try:
            generated = generate_image_with_gemini(image_spec["prompt"])
            image_path = str(generated) if generated else None
        except Exception as exc:
            log.warning("Image generation failed, continuing without generated image: %s", exc)

    return save_draft(content, platforms, posts, context, image_path, image_url)


def maybe_publish_after_approval(draft_path: Path, args: argparse.Namespace) -> None:
    if args.dry_run:
        print("\nDry-run only. Nothing was published.")
        return
    if REQUIRE_APPROVAL and not args.auto_publish:
        if sys.stdin.isatty():
            choice = input("\nPublish this draft now? Type 'yes' to approve: ").strip().lower()
            if choice == "yes":
                print(json.dumps(publish_draft(draft_path), indent=2))
                return
        print(f"\nNot published. Approve later with:\n  python social_agent.py --approve \"{draft_path}\"")
        return
    print(json.dumps(publish_draft(draft_path), indent=2))


def run_once(args: argparse.Namespace) -> None:
    draft_path = create_draft(args)
    print_draft_preview(draft_path)
    maybe_publish_after_approval(draft_path, args)


def run_schedule(args: argparse.Namespace) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    hour, minute = map(int, os.environ.get("POST_TIME", "09:00").split(":"))
    scheduler = BlockingScheduler()

    def job() -> None:
        run_once(args)

    scheduler.add_job(job, "cron", hour=hour, minute=minute)
    log.info("Scheduler started. Daily run time: %02d:%02d local time.", hour, minute)
    scheduler.start()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG-powered social media manager with approval-gated publishing.")
    parser.add_argument("--ingest", action="store_true", help="Ingest approved local source folders into ChromaDB.")
    parser.add_argument("--sources", nargs="*", help="Folders/files to ingest. Defaults to knowledge_base.")
    parser.add_argument("--reset-rag", action="store_true", help="Delete and rebuild the RAG collection before ingesting.")
    parser.add_argument("--check-access", action="store_true", help="Validate configured platform credentials.")
    parser.add_argument("--once", action="store_true", help="Create one draft from topic/url/youtube or rotating topics.")
    parser.add_argument("--schedule", action="store_true", help="Run daily at POST_TIME.")
    parser.add_argument("--approve", help="Publish a saved draft JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Generate/preview without publishing.")
    parser.add_argument("--auto-publish", action="store_true", help="Publish after drafting in this run. Use carefully.")
    parser.add_argument("--platforms", default=None, help="Comma list: linkedin,instagram,reddit.")
    parser.add_argument("--topic", help="Topic or raw idea for the post.")
    parser.add_argument("--url", help="Article/blog URL to repurpose.")
    parser.add_argument("--youtube", help="YouTube URL or video ID to repurpose.")
    parser.add_argument("--image", help="Local image path to attach where supported.")
    parser.add_argument("--image-url", help="Public image URL, required for Instagram publishing.")
    parser.add_argument("--top-k", type=int, default=6, help="Number of RAG chunks to retrieve.")
    return parser.parse_args()


def interactive() -> None:
    print("Social Media Manager Agent")
    print("Paste a topic, article URL, YouTube URL, or press Enter for the next topic.")
    value = input("> ").strip()
    args = parse_args()
    args.once = True
    if not value:
        pass
    elif "youtube.com" in value or "youtu.be" in value:
        args.youtube = value
    elif value.startswith("http://") or value.startswith("https://"):
        args.url = value
    else:
        args.topic = value
    run_once(args)


def main() -> None:
    args = parse_args()
    if args.ingest:
        count = ingest_sources(args.sources or [], reset=args.reset_rag)
        print(f"Ingested {count} chunks into {DB_DIR}")
    if args.check_access:
        print(json.dumps(check_access(clean_platforms(args.platforms)), indent=2))
    if args.approve:
        print(json.dumps(publish_draft(Path(args.approve), dry_run=args.dry_run), indent=2))
    if args.once:
        run_once(args)
    if args.schedule:
        run_schedule(args)
    if not any([args.ingest, args.check_access, args.approve, args.once, args.schedule]):
        interactive()


if __name__ == "__main__":
    main()
