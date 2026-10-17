"""
Reference Image Analysis Skill
------------------------------
Analyzes uploaded images for composition, lighting, colors, visual hierarchy,
subject placement, typography, and design style, converting them into a reusable VisualBrief.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List, Tuple
from PIL import Image, ImageStat

log = logging.getLogger("reference_analysis")


@dataclass
class VisualBrief:
    style_category: str
    dominant_colors: List[str]
    lighting_style: str
    contrast_level: str
    composition: str
    subject_placement: str
    aspect_ratio: str
    width: int
    height: int
    recommended_prompt_modifiers: str
    preserve_subject: bool = False
    reference_id: str = ""
    extra_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReferenceImageAnalyzer:
    @staticmethod
    def analyze(image_path: Path | str, preserve_subject: bool = False) -> VisualBrief:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Reference image not found: {path}")

        try:
            with Image.open(path) as img:
                img_rgb = img.convert("RGB")
                w, h = img_rgb.size
                aspect = f"{w}:{h}"
                if abs(w / h - 1.91) < 0.15:
                    aspect_label = "1.91:1 (LinkedIn Feed)"
                elif abs(w / h - 1.0) < 0.1:
                    aspect_label = "1:1 (Square)"
                elif abs(w / h - 0.8) < 0.1:
                    aspect_label = "4:5 (Portrait Carousel)"
                else:
                    aspect_label = f"{round(w/h, 2)}:1"

                # 1. Palette extraction
                palette_img = img_rgb.quantize(colors=5)
                palette_colors = palette_img.getpalette()[:15]
                hex_colors = []
                for i in range(0, len(palette_colors), 3):
                    r, g, b = palette_colors[i : i + 3]
                    hex_colors.append(f"#{r:02x}{g:02x}{b:02x}")

                # 2. Lighting & Brightness
                stat = ImageStat.Stat(img_rgb)
                mean_brightness = sum(stat.mean) / 3.0
                if mean_brightness < 70:
                    lighting = "Dark mode / Deep obsidian with vibrant neon accents"
                    style_category = "Minimalist Dark Tech & 3D Isometric"
                elif mean_brightness > 180:
                    lighting = "High-key / Clean minimal light theme"
                    style_category = "Editorial Clean Tech Graphic"
                else:
                    lighting = "Balanced studio lighting with controlled directional shadows"
                    style_category = "Modern 3D Technical Infographic"

                # 3. Contrast analysis
                stddev = sum(stat.stddev) / 3.0
                contrast = "High contrast" if stddev > 45 else "Muted / Low contrast"

                # 4. Composition heuristic
                composition = "Rule-of-thirds with clean negative space for typography" if (w > h) else "Centered focal hierarchy"
                subject_placement = "Offset left-center" if (w > h) else "Center-weighted"

                modifiers = (
                    f"style inspired by reference ({style_category}), color tones featuring {', '.join(hex_colors[:3])}, "
                    f"{lighting}, clean 8k octane render, professional software engineering aesthetic, no messy text"
                )

                brief = VisualBrief(
                    style_category=style_category,
                    dominant_colors=hex_colors,
                    lighting_style=lighting,
                    contrast_level=contrast,
                    composition=composition,
                    subject_placement=subject_placement,
                    aspect_ratio=aspect_label,
                    width=w,
                    height=h,
                    recommended_prompt_modifiers=modifiers,
                    preserve_subject=preserve_subject,
                    reference_id=path.name,
                    extra_notes=[
                        f"Mean Brightness: {mean_brightness:.1f}/255",
                        f"Contrast StdDev: {stddev:.1f}",
                    ],
                )
                log.info("Visual brief generated for %s: %s", path.name, brief.style_category)
                return brief
        except Exception as exc:
            log.warning("Reference analysis failed, using fallback visual brief: %s", exc)
            return VisualBrief(
                style_category="Modern 3D Technical Infographic",
                dominant_colors=["#00E5FF", "#7C4DFF", "#0B0F17"],
                lighting_style="Dark mode with glowing neon cyan/purple accents",
                contrast_level="High contrast",
                composition="Clean negative space with right-balanced focal point",
                subject_placement="Focal center",
                aspect_ratio="1.91:1 (LinkedIn Feed)",
                width=1200,
                height=627,
                recommended_prompt_modifiers="3D isometric backend system architecture, glowing cyan and violet data nodes, dark obsidian background, 8k octane render",
                reference_id=path.name if path else "none",
            )
