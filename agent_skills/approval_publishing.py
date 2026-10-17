"""
Approval and Publishing Skill
-----------------------------
Manages draft inspection, terminal approval dashboards, and verified LinkedIn publishing
via the official REST Posts and Images API.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Tuple
import requests

log = logging.getLogger("approval_publishing")


class ApprovalManager:
    @staticmethod
    def render_approval_card(
        topic: str,
        post_text: str,
        image_path: Path | str,
        qa_score: float,
        visual_concept: str,
        is_repetitive: bool = False,
        repetition_reason: str = "",
    ) -> None:
        """Prints a rich terminal approval card for the developer."""
        print("\n" + "=" * 74)
        print("          🔍 LINKEDIN AGENT APPROVAL & QUALITY DASHBOARD          ")
        print("=" * 74)
        print(f"📌 TOPIC:          {topic}")
        print(f"🎯 VISUAL CONCEPT: {visual_concept}")
        print(f"🖼️ FINAL ASSET:    {image_path}")
        print(f"⭐ QA SCORE:       {qa_score:.1f}/100 {'✅ (Passed)' if qa_score >= 70 else '⚠️ (Review needed)'}")
        if is_repetitive:
            print(f"⚠️ REPETITION:     {repetition_reason}")
        else:
            print("✨ ORIGINALITY:    Verified against recent content memory")
        print("-" * 74)
        print("CAPTION PREVIEW:")
        print("-" * 74)
        print(post_text)
        print("-" * 74)

    @staticmethod
    def publish_to_linkedin(
        post_text: str,
        image_path: Path | str | None,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        """
        Publishes post and image using LinkedIn REST API.
        Guarantees that post is only marked published upon positive confirmation.
        """
        if dry_run:
            log.info("Dry run active: Post simulated without API dispatch.")
            return True, "dry-run-simulated"

        from agent_skills.content_memory import ContentMemory
        mem = ContentMemory()
        can_post, reason = mem.can_post_today(min_hours_gap=20.0)
        if not can_post:
            log.error("Posting rejected by 1-post-per-day policy: %s", reason)
            return False, f"BLOCKED by 1-post-per-day limit: {reason}"

        token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        if not token:
            raise ValueError("LINKEDIN_ACCESS_TOKEN is missing from environment.")

        # Resolve author
        author_urn = os.environ.get("LINKEDIN_PERSON_URN")
        if not author_urn or not author_urn.startswith("urn:li:person:"):
            u_res = requests.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {token}"}, timeout=20)
            u_res.raise_for_status()
            author_urn = f"urn:li:person:{u_res.json()['sub']}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": os.environ.get("LINKEDIN_VERSION", "202603"),
        }

        image_urn = None
        if image_path and Path(image_path).exists():
            log.info("Initializing LinkedIn media upload...")
            init_res = requests.post(
                "https://api.linkedin.com/rest/images?action=initializeUpload",
                headers=headers,
                json={"initializeUploadRequest": {"owner": author_urn}},
                timeout=30,
            )
            init_res.raise_for_status()
            init_data = init_res.json()["value"]
            upload_url = init_data["uploadUrl"]
            image_urn = init_data["image"]

            log.info("Streaming image binary to LinkedIn CDN...")
            with open(image_path, "rb") as f:
                up_res = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                    data=f,
                    timeout=60,
                )
            up_res.raise_for_status()
            log.info("Image registered on LinkedIn: %s", image_urn)

        # Build post payload
        # Sanitize little text characters
        clean_text = post_text.replace("`", "").replace("([()[\\]{}<>|])", "\\\\$1")
        payload: dict[str, Any] = {
            "author": author_urn,
            "commentary": clean_text.strip(),
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

        log.info("Dispatching post payload to LinkedIn...")
        post_res = requests.post("https://api.linkedin.com/rest/posts", headers=headers, json=payload, timeout=30)
        post_res.raise_for_status()

        post_id = post_res.headers.get("x-restli-id", "published-success")
        log.info("Successfully published post to LinkedIn! Post URN: %s", post_id)
        return True, post_id
