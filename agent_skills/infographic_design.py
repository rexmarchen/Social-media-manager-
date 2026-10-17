"""
Infographic and Carousel Design Skill
-------------------------------------
Generates deterministic technical comparison cards, architectural diagrams,
and consistent multi-slide carousel assets for educational LinkedIn engagement.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
from .brand_consistency import BrandManager

log = logging.getLogger("infographic_design")

ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT_DIR / "generated_images"
GENERATED_DIR.mkdir(exist_ok=True)


class InfographicDesigner:
    def __init__(self, brand_manager: BrandManager | None = None):
        self.brand = brand_manager or BrandManager()

    def _get_font(self, size: int) -> ImageFont.ImageFont:
        for name in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def create_comparison_card(
        self,
        title: str,
        left_label: str,
        left_points: List[str],
        right_label: str,
        right_points: List[str],
        width: int = 1200,
        height: int = 627,
    ) -> Path:
        """
        Creates a side-by-side architectural comparison graphic (e.g., Redis vs In-Memory).
        """
        img = Image.new("RGB", (width, height), color=self.brand.get_color("background_dark"))
        draw = ImageDraw.Draw(img)

        # Title font
        t_font = self._get_font(38)
        header_font = self._get_font(26)
        body_font = self._get_font(20)

        # Header Title
        draw.text((70, 45), title, font=t_font, fill=self.brand.get_color("text_primary"))

        # Column Layout
        col_w = (width - 180) // 2
        col_h = height - 190
        col_y = 120

        # Left Column (e.g. Traditional / Anti-pattern)
        draw.rounded_rectangle(
            [(70, col_y), (70 + col_w, col_y + col_h)],
            radius=12,
            fill=self.brand.get_color("surface_dark"),
            outline=self.brand.get_color("card_border"),
            width=2,
        )
        draw.text((95, col_y + 25), left_label, font=header_font, fill=self.brand.get_color("accent_warning"))

        curr_y = col_y + 75
        for pt in left_points[:4]:
            draw.text((95, curr_y), f"• {pt}", font=body_font, fill=self.brand.get_color("text_muted"))
            curr_y += 38

        # Right Column (e.g. Optimized / Recommended Architecture)
        right_x = 70 + col_w + 40
        draw.rounded_rectangle(
            [(right_x, col_y), (right_x + col_w, col_y + col_h)],
            radius=12,
            fill=self.brand.get_color("surface_dark"),
            outline=self.brand.get_color("primary"),
            width=2,
        )
        draw.text((right_x + 25, col_y + 25), right_label, font=header_font, fill=self.brand.get_color("primary"))

        curr_y = col_y + 75
        for pt in right_points[:4]:
            draw.text((right_x + 25, curr_y), f"✓ {pt}", font=body_font, fill=self.brand.get_color("text_primary"))
            curr_y += 38

        # Footer
        footer_y = height - 45
        footer_text = f"{self.brand.brand_name} • {self.brand.handle} • {self.brand.config.get('github', '')}"
        draw.text((70, footer_y), footer_text, font=self._get_font(18), fill=self.brand.get_color("text_muted"))

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = GENERATED_DIR / f"comparison-{timestamp}.jpg"
        img.save(out_path, "JPEG", quality=95)
        log.info("Comparison infographic generated: %s", out_path)
        return out_path

    def create_carousel(
        self,
        slides_data: List[dict[str, Any]],
        width: int = 1080,
        height: int = 1080,
    ) -> List[Path]:
        """
        Creates a sequence of square or 4:5 carousel slides for LinkedIn documents/carousels.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        paths: List[Path] = []
        total = len(slides_data)

        for idx, slide in enumerate(slides_data, start=1):
            img = Image.new("RGB", (width, height), color=self.brand.get_color("background_dark"))
            draw = ImageDraw.Draw(img)

            # Slide progress indicator
            draw.text((width - 140, 60), f"{idx} / {total}", font=self._get_font(22), fill=self.brand.get_color("primary"))

            # Slide Badge / Category
            badge = slide.get("badge", "ARCHITECTURE GUIDE").upper()
            draw.rounded_rectangle([(80, 60), (320, 100)], radius=6, fill=self.brand.get_color("surface_dark"))
            draw.text((95, 68), badge, font=self._get_font(18), fill=self.brand.get_color("primary"))

            # Title
            title = slide.get("title", f"Step {idx}")
            draw.text((80, 160), title, font=self._get_font(46), fill=self.brand.get_color("text_primary"))

            # Body lines
            curr_y = 260
            for line in slide.get("body", []):
                draw.text((80, curr_y), line, font=self._get_font(28), fill=self.brand.get_color("text_muted"))
                curr_y += 50

            # Footer
            draw.text((80, height - 70), f"{self.brand.brand_name} • {self.brand.handle}", font=self._get_font(20), fill=self.brand.get_color("text_muted"))

            slide_path = GENERATED_DIR / f"carousel-{timestamp}-slide{idx}.jpg"
            img.save(slide_path, "JPEG", quality=95)
            paths.append(slide_path)

        log.info("Created %d carousel slides in %s", len(paths), GENERATED_DIR)
        return paths
