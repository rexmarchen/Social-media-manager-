"""
Image Editing and Composition Skill
-----------------------------------
Applies deterministic text layout, brand badges, contrast-backing cards,
and precise LinkedIn dimension scaling (1200x627) via Pillow.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .brand_consistency import BrandManager

log = logging.getLogger("image_composition")


class ImageCompositor:
    def __init__(self, brand_manager: BrandManager | None = None):
        self.brand = brand_manager or BrandManager()

    def _get_font(self, size: int) -> ImageFont.ImageFont:
        # Try loading common system fonts, fallback to default bitmap font
        for name in ["arial.ttf", "segoeui.ttf", "calibri.ttf", "Helvetica.ttf"]:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current: list[str] = []

        for word in words:
            test_line = " ".join(current + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]

        if current:
            lines.append(" ".join(current))
        return lines[:3]  # Keep max 3 lines for high-impact title

    def compose(
        self,
        base_image_path: Path | str,
        title: str,
        subtitle: str | None = None,
        tag: str | None = None,
        target_dimensions: Tuple[int, int] = (1200, 627),
    ) -> Path:
        """
        Overlays brand elements, title, tag, and watermark over base image.
        Returns the path to the composited final image.
        """
        base_path = Path(base_image_path)
        img = Image.open(base_path).convert("RGB")

        # 1. Resize and crop to exact target dimensions
        target_w, target_h = target_dimensions
        orig_w, orig_h = img.size
        orig_aspect = orig_w / orig_h
        target_aspect = target_w / target_h

        if orig_aspect > target_aspect:
            # Crop width
            new_w = int(orig_h * target_aspect)
            left = (orig_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, orig_h))
        else:
            # Crop height
            new_h = int(orig_w / target_aspect)
            top = (orig_h - new_h) // 2
            img = img.crop((0, top, orig_w, top + new_h))

        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 2. Add subtle dark overlay on the left 60% for optimal text legibility
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        # Horizontal gradient overlay
        for x in range(int(target_w * 0.70)):
            alpha = int(190 * (1.0 - (x / (target_w * 0.70)) ** 1.3))
            draw_ov.line([(x, 0), (x, target_h)], fill=(11, 15, 23, alpha))

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 3. Typography setup
        title_font = self._get_font(self.brand.config["typography"]["title_size"])
        sub_font = self._get_font(self.brand.config["typography"]["subtitle_size"])
        tag_font = self._get_font(self.brand.config["typography"]["tag_size"])

        primary_rgb = self.brand.get_color("primary")
        text_primary_rgb = self.brand.get_color("text_primary")
        text_muted_rgb = self.brand.get_color("text_muted")
        surface_dark_rgb = self.brand.get_color("surface_dark")
        border_rgb = self.brand.get_color("card_border")

        margin_x = 70
        curr_y = 65

        # 4. Brand Category Tag / Badge
        tag_text = (tag or self.brand.tagline).upper()
        tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        tag_w = tag_bbox[2] - tag_bbox[0] + 28
        tag_h = tag_bbox[3] - tag_bbox[1] + 14

        draw.rounded_rectangle(
            [(margin_x, curr_y), (margin_x + tag_w, curr_y + tag_h)],
            radius=6,
            fill=surface_dark_rgb,
            outline=border_rgb,
            width=1,
        )
        draw.text((margin_x + 14, curr_y + 6), tag_text, font=tag_font, fill=primary_rgb)
        curr_y += tag_h + 35

        # 5. Main Title (Wrapped)
        max_text_w = int(target_w * 0.55)
        title_lines = self._wrap_text(title, title_font, max_text_w, draw)
        for line in title_lines:
            draw.text((margin_x, curr_y), line, font=title_font, fill=text_primary_rgb)
            curr_y += self.brand.config["typography"]["title_size"] + 12

        curr_y += 10

        # 6. Subtitle / Architectural note
        if subtitle:
            sub_lines = self._wrap_text(subtitle, sub_font, max_text_w, draw)
            for s_line in sub_lines[:2]:
                draw.text((margin_x, curr_y), s_line, font=sub_font, fill=text_muted_rgb)
                curr_y += self.brand.config["typography"]["subtitle_size"] + 8

        # 7. Bottom Brand Watermark
        if self.brand.config.get("watermark_enabled", True):
            footer_y = target_h - 55
            draw.line([(margin_x, footer_y - 15), (margin_x + 350, footer_y - 15)], fill=border_rgb, width=1)
            watermark_text = f"{self.brand.brand_name} • {self.brand.handle} • {self.brand.config.get('github', '')}"
            draw.text((margin_x, footer_y), watermark_text, font=tag_font, fill=text_muted_rgb)

        # Save composited output
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = base_path.parent / f"final-{timestamp}.jpg"
        img.save(out_path, "JPEG", quality=95)
        log.info("Composited professional image saved: %s", out_path)
        return out_path
