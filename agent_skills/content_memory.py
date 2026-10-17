"""
Content Memory Skill
--------------------
Maintains a persistent record of previously generated posts, hooks, prompts,
visual briefs, QA scores, and publishing status to eliminate repetition.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

log = logging.getLogger("content_memory")

ROOT_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT_DIR / "content_memory.json"


class ContentMemory:
    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or MEMORY_FILE
        self.records: List[dict[str, Any]] = self._load()

    def _load(self) -> List[dict[str, Any]]:
        if self.storage_path.exists():
            try:
                return json.loads(self.storage_path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("Could not read content memory: %s", e)
        return []

    def _save(self) -> None:
        try:
            self.storage_path.write_text(json.dumps(self.records, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning("Could not persist content memory: %s", e)

    def record_post(
        self,
        topic: str,
        category: str,
        caption: str,
        hook: str,
        image_prompt: str,
        visual_brief: dict[str, Any],
        image_path: str,
        qa_score: float,
        reference_id: str = "none",
        model_name: str = "flux-synthesis",
        status: str = "draft",
    ) -> str:
        """Appends a new generation record to persistent memory."""
        post_id = f"mem-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        entry = {
            "post_id": post_id,
            "created_at": datetime.now().isoformat(),
            "topic": topic,
            "category": category,
            "hook": hook,
            "caption_snippet": caption[:150] + "...",
            "image_prompt": image_prompt,
            "visual_brief": visual_brief,
            "reference_id": reference_id,
            "model_settings": {"model": model_name, "dimensions": [1200, 627]},
            "output_asset_path": str(image_path),
            "qa_score": qa_score,
            "status": status,
            "performance_metrics": {},
        }
        self.records.append(entry)
        self._save()
        log.info("Recorded post to content memory: %s (%s)", post_id, topic)
        return post_id

    def check_repetition(self, candidate_topic: str, candidate_hook: str = "", lookback: int = 15) -> tuple[bool, str]:
        """
        Inspects recent history to detect repetitive topics or recycled hooks.
        """
        recent = self.records[-lookback:] if len(self.records) > lookback else self.records
        cand_topic_words = set(candidate_topic.lower().split())

        for item in recent:
            past_topic = item.get("topic", "")
            past_words = set(past_topic.lower().split())
            intersection = cand_topic_words.intersection(past_words)

            if len(cand_topic_words) > 0 and len(intersection) / len(cand_topic_words) > 0.70:
                return True, f"Topic strongly overlaps with recent post: '{past_topic}'"

            past_hook = item.get("hook", "")
            if candidate_hook and past_hook and candidate_hook.lower() == past_hook.lower():
                return True, f"Hook is identical to recent post from {item.get('created_at')}"

        return False, "Original content verified"

    def mark_published(self, post_id: str, linkedin_post_urn: str) -> None:
        for item in self.records:
            if item.get("post_id") == post_id:
                item["status"] = "published"
                item["linkedin_post_urn"] = linkedin_post_urn
                item["published_at"] = datetime.now().isoformat()
                self._save()
                break

    def can_post_today(self, min_hours_gap: float = 20.0) -> tuple[bool, str]:
        """
        Enforces maximum 1 post per day. Checks if any post was already published today
        or within min_hours_gap hours.
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        for item in reversed(self.records):
            if item.get("status") == "published":
                pub_time_str = item.get("published_at") or item.get("created_at")
                if pub_time_str:
                    try:
                        pub_time = datetime.fromisoformat(pub_time_str)
                        # Check same calendar day
                        if pub_time.strftime("%Y-%m-%d") == today_str:
                            return False, f"A post was already published today ({today_str}) at {pub_time.strftime('%H:%M:%S')}: '{item.get('topic')}'"
                        
                        # Check elapsed hours gap
                        elapsed = (now - pub_time).total_seconds() / 3600.0
                        if elapsed < min_hours_gap:
                            return False, f"Post gap active: last post was published {elapsed:.1f} hours ago. Minimum {min_hours_gap} hours required."
                    except Exception:
                        pass

        return True, "Ready to post (1-post-per-day limit satisfied)"

    def get_recent(self, limit: int = 5) -> List[dict[str, Any]]:
        return self.records[-limit:] if len(self.records) > limit else self.records
