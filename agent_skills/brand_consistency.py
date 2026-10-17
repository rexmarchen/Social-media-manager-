"""
Brand Consistency Skill
------------------------
Enforces approved logos, colors, typography, visual guidelines, and reusable design templates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Tuple

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "brand_guidelines.json"


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    hex_code = hex_code.lstrip("#")
    if len(hex_code) == 3:
        hex_code = "".join([c * 2 for c in hex_code])
    return int(hex_code[0:2], 16), int(hex_code[2:4], 16), int(hex_code[4:6], 16)


class BrandManager:
    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "brand_name": "Anshu Pal",
            "handle": "@rexmarchen",
            "github": "github.com/rexmarchen",
            "flagship_project": "REXION",
            "tagline": "AI & Full-Stack Systems",
            "colors": {
                "primary": "#00E5FF",
                "secondary": "#7C4DFF",
                "background_dark": "#0B0F17",
                "surface_dark": "#161B22",
                "card_border": "#30363D",
                "text_primary": "#F0F6FC",
                "text_muted": "#8B949E",
                "accent_success": "#39D353",
                "accent_warning": "#F5A623",
            },
            "typography": {
                "title_size": 42,
                "subtitle_size": 22,
                "tag_size": 18,
                "font_family": "Arial",
            },
            "dimensions": {
                "linkedin_feed": [1200, 627],
                "square": [1080, 1080],
                "carousel": [1080, 1350],
            },
            "watermark_enabled": True,
            "qa_thresholds": {
                "min_width": 1200,
                "min_height": 627,
                "min_sharpness": 10.0,
                "min_contrast": 20.0,
                "pass_score": 75.0,
                "max_retries": 2,
            },
        }

    @property
    def brand_name(self) -> str:
        return self.config.get("brand_name", "Anshu Pal")

    @property
    def handle(self) -> str:
        return self.config.get("handle", "@rexmarchen")

    @property
    def tagline(self) -> str:
        return self.config.get("tagline", "AI & Full-Stack Systems")

    def get_color(self, name: str) -> Tuple[int, int, int]:
        colors = self.config.get("colors", {})
        hex_code = colors.get(name, "#00E5FF" if name == "primary" else "#0B0F17")
        return hex_to_rgb(hex_code)

    def get_dimensions(self, layout: str = "linkedin_feed") -> Tuple[int, int]:
        dims = self.config.get("dimensions", {}).get(layout, [1200, 627])
        return dims[0], dims[1]

    def get_qa_thresholds(self) -> dict[str, Any]:
        return self.config.get("qa_thresholds", {
            "min_width": 1200,
            "min_height": 627,
            "min_sharpness": 10.0,
            "min_contrast": 20.0,
            "pass_score": 75.0,
            "max_retries": 2,
        })
