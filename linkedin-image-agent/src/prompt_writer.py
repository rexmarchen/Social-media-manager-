"""
prompt_writer.py - Generates structured Flux LoRA prompts adhering to brand aesthetic rules.
Enforces the master formula:
[trigger_word], [subject / concept], [materials & props], [lighting & camera], [palette], [negative space]
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import yaml
from pydantic import BaseModel

from src.llm import get_llm, LLMClient


class GeneratedPrompt(BaseModel):
    topic: str
    headline: str
    positive_prompt: str
    negative_prompt: str
    layout_type: str  # "headline-on-photo" | "photo-only" | "quote-card"
    negative_space_zone: str  # "top" | "bottom" | "center"


DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low resolution, bad anatomy, garbled illegible text, fake AI gibberish letters, "
    "3d cartoon render, pixar style, glossy plastic sheen, oversaturated neon rainbow glow, "
    "generic corporate stock photography, cluttered background, lack of negative space"
)


class PromptWriter:
    def __init__(self, brand_config_path: Path, style_guide_path: Optional[Path] = None):
        self.brand_config_path = Path(brand_config_path)
        self.style_guide_path = Path(style_guide_path) if style_guide_path else None
        self._load_config()

    def _load_config(self):
        with open(self.brand_config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.brand_name = self.config.get("brand", {}).get("name", "Anshu Pal")
        self.flagship = self.config.get("brand", {}).get("flagship", "REXION")
        self.trigger_word = self.config.get("trigger_word", "rexstyle")
        self.colors = self.config.get("colors", {})
        self.primary_hex = self.colors.get("primary", "#1832D7")
        self.secondary_hex = self.colors.get("secondary", "#F5BA04")
        self.accent_hex = self.colors.get("accent", "#E85A18")

        self.style_guide_text = ""
        if self.style_guide_path and self.style_guide_path.exists():
            with open(self.style_guide_path, "r", encoding="utf-8") as f:
                self.style_guide_text = f.read()[:1500]

    def build_prompt_with_llm(
        self,
        topic: str,
        layout_type: str = "headline-on-photo",
        llm: Optional[LLMClient] = None,
    ) -> GeneratedPrompt:
        """Uses LLM to construct an on-brand prompt tailored to the topic."""
        llm = llm or get_llm()

        system_instruction = (
            f"You are a master Flux prompt engineer for {self.flagship} ({self.brand_name}).\n"
            f"The image generator requires the trigger word '{self.trigger_word}' at the start.\n"
            f"Brand colors: Cobalt Blue ({self.primary_hex}), Mustard Yellow ({self.secondary_hex}), Terracotta ({self.accent_hex}).\n"
            f"Aesthetic: Tactile retro-futuristic engineering, vintage CRT/mechanical hardware, clean editorial minimalism, flat lay or studio 45-degree angle.\n"
            f"Crucial Requirement: Must reserve at least 40% empty/flat negative space (usually in the upper half) for crisp typography overlay.\n"
            f"Never request garbled or AI-generated text inside the image. The image must remain clean and photographic/tactile."
        )

        user_query = (
            f"Generate a Flux LoRA prompt for the following LinkedIn post topic:\n"
            f"Topic: {topic}\n"
            f"Layout Style: {layout_type}\n\n"
            f"Return JSON strictly with the keys:\n"
            f"- 'headline': punchy 4 to 8 word headline suitable for the post\n"
            f"- 'positive_prompt': single cohesive paragraph starting with '{self.trigger_word}, '\n"
            f"- 'negative_space_zone': 'top' or 'bottom'\n"
            f"JSON ONLY."
        )

        data = None
        try:
            raw = llm.generate_text(user_query, system_prompt=system_instruction)
            clean = raw.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            import json
            data = json.loads(clean)
        except Exception:
            data = None

        if not data:
            data = {
                "headline": f"Mastering {topic}",
                "positive_prompt": (
                    f"{self.trigger_word}, tactile retro-tech studio still life representing {topic}. "
                    f"Vintage CRT computer terminal with mechanical keyboard on a warm off-white drafting table. "
                    f"Clean matte solid background, cobalt blue ({self.primary_hex}) and mustard ({self.secondary_hex}) accents. "
                    f"Spacious clean negative space in upper 45% of composition, soft diffused overhead lighting, 35mm film grain, editorial quality."
                ),
                "negative_space_zone": "top",
            }

        pos_prompt = data.get("positive_prompt", "").strip()
        if not pos_prompt.lower().startswith(self.trigger_word.lower()):
            pos_prompt = f"{self.trigger_word}, {pos_prompt}"

        return GeneratedPrompt(
            topic=topic,
            headline=data.get("headline", topic),
            positive_prompt=pos_prompt,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            layout_type=layout_type,
            negative_space_zone=data.get("negative_space_zone", "top"),
        )
