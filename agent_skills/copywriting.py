"""
LinkedIn Copywriting Skill
--------------------------
Crafts high-engagement, humanized engineering posts with scroll-stopping hooks,
practical architectural depth, and zero AI clichés.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
import requests

log = logging.getLogger("copywriting")

BANNED_WORDS = [
    "delve", "tapestry", "testament", "beacon", "game-changer", "revolutionize",
    "embark", "landscape", "bespoke", "leverage", "seamless", "transformative",
    "supercharge", "dive into", "in today's world", "thrilled to announce",
    "delighted to share", "humble brag", "thought leader"
]


class LinkedInCopywriter:
    def __init__(self):
        self.banned_regex = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.IGNORECASE)

    def _clean_ai_cliches(self, text: str) -> str:
        """Strips or replaces banned AI buzzwords."""
        replacements = {
            r"\bdelve into\b": "explore",
            r"\bleverage\b": "use",
            r"\bseamless\b": "smooth",
            r"\bgame-changer\b": "significant shift",
            r"\bsupercharge\b": "accelerate",
            r"\btapestry\b": "system",
        }
        cleaned = text
        for pat, rep in replacements.items():
            cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
        return cleaned

    def draft_post(self, topic: str, context: str, rag_snippets: str = "") -> dict[str, str]:
        """
        Generates post text and visual prompt via Gemini, Claude, or OpenAI.
        """
        gemini_key = os.environ.get("GEMINI_API_KEY")
        prompt = f"""You are Anshu Pal, a B.Tech student in Artificial Intelligence and Machine Learning at CGC University, building REXION (AI job discovery platform) and backend systems.

TOPIC: {topic}
TECHNICAL CONTEXT / REAL EXPERIENCE:
{context}
{rag_snippets}

CRITICAL RULES:
1. Hook: Start directly with a concrete problem, counter-intuitive insight, or debugging finding. NO generic intros like "In today's fast paced world", "I am thrilled to share", or "Have you ever wondered".
2. Story / Architecture: Explain the actual trade-off, technical hurdle, or metric (e.g. p95/p99 latency, database scanning, WebSocket state).
3. The Lesson: What actually worked in practice.
4. Discussion Question: End with an intelligent, open-ended question that tech leads would love to answer.
5. Hashtags: 3-5 clean dev hashtags (e.g. #BackendEngineering #SystemDesign #MongoDB #WebDev #AIML).
6. BANNED CLICHÉ WORDS (NEVER USE): delve, tapestry, testament, beacon, game-changer, revolutionize, embark, landscape, bespoke, leverage, seamless, transformative, supercharge, dive into.
7. Length: 120 - 180 words. Mobile-friendly spacing with short paragraphs.

IMAGE PROMPT REQUIREMENT:
Design a prompt for a high-definition, visually stunning graphic to accompany this post.
Style: Sleek modern 3D isometric or dark-mode tech architectural infographic. Rich glowing cyan/purple lighting on deep obsidian background. Minimalist, professional, high-end 8k render. Do NOT include messy unreadable text in the image.

Respond ONLY with valid JSON:
{{
  "hook": "<the 1-line opening hook>",
  "post_text": "<complete post with comfortable line breaks and hashtags>",
  "image_concept": "<short 1-line concept title>",
  "image_prompt": "<detailed visual prompt for generating the 1200x627 graphic>"
}}"""

        if gemini_key:
            try:
                candidate_models = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-flash-latest"]
                for model in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                    resp = requests.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=25
                    )
                    if resp.status_code == 200:
                        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        match = re.search(r"\{[\s\S]*\}", raw)
                        if match:
                            data = json.loads(match.group(0))
                            data["post_text"] = self._clean_ai_cliches(data["post_text"])
                            return data
            except Exception as e:
                log.warning("Gemini copywriting failed, falling back: %s", e)

        # Fallback template
        fallback_text = (
            f"When scaling backend systems, the biggest trap is optimizing the wrong metric.\n\n"
            f"While working on {topic}, we noticed that looking at average latency masked huge p99 spikes. "
            f"By analyzing actual query profiles and execution stats rather than guessing, "
            f"we identified exactly where the bottlenecks were.\n\n"
            f"The real lesson: measure first, profile the queries, and then add caching or indexes where they actually matter.\n\n"
            f"What is your primary go-to tool when profiling database bottlenecks?\n\n"
            f"#BackendEngineering #SoftwareArchitecture #SystemDesign #Database"
        )
        return {
            "hook": "When scaling backend systems, the biggest trap is optimizing the wrong metric.",
            "post_text": fallback_text,
            "image_concept": f"Technical Architecture for {topic}",
            "image_prompt": f"Minimalist 3D isometric dark-mode render of {topic}, glowing cyan and purple server nodes, 8k octane render",
        }
