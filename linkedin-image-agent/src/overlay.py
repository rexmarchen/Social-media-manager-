"""
overlay.py - PIL Typography and Layout Engine for LinkedIn Visuals.
Renders brand typography with auto-wrapping, safe margin bounding, and high contrast.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont
import yaml


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Converts #RRGGBB to (R, G, B)."""
    hex_code = hex_code.lstrip("#")
    return tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


class TypographyEngine:
    def __init__(self, brand_config_path: Path):
        self.config_path = Path(brand_config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.fonts_cfg = self.config.get("fonts", {})
        self.colors_cfg = self.config.get("colors", {})
        self.brand_cfg = self.config.get("brand", {})

        # Font paths
        base_dir = self.config_path.parent.parent
        self.heading_font_path = base_dir / self.fonts_cfg.get("heading", "assets/fonts/heading.ttf")
        self.body_font_path = base_dir / self.fonts_cfg.get("body", "assets/fonts/body.ttf")

        # Color palette
        self.c_primary = hex_to_rgb(self.colors_cfg.get("primary", "#1832D7"))
        self.c_secondary = hex_to_rgb(self.colors_cfg.get("secondary", "#F5BA04"))
        self.c_accent = hex_to_rgb(self.colors_cfg.get("accent", "#E85A18"))
        self.c_bg_light = hex_to_rgb(self.colors_cfg.get("background_light", "#FAF8F5"))
        self.c_bg_dark = hex_to_rgb(self.colors_cfg.get("background_dark", "#0F1218"))
        self.c_text_dark = hex_to_rgb(self.colors_cfg.get("text_dark", "#1A1A1E"))
        self.c_text_light = hex_to_rgb(self.colors_cfg.get("text_light", "#FFFFFF"))

    def get_font(self, font_type: str, size: int) -> ImageFont.FreeTypeFont:
        font_path = self.heading_font_path if font_type == "heading" else self.body_font_path
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            return ImageFont.load_default()

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
        """Wraps text so no line exceeds max_width."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            candidate = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def apply_overlay(
        self,
        image_input: Image.Image,
        headline: str,
        layout_type: str = "headline-on-photo",
        text_zone: str = "top",
        subheading: Optional[str] = None,
    ) -> Image.Image:
        """
        Applies brand typography overlay onto image.
        layout_type: 'photo-only' | 'headline-on-photo' | 'quote-card'
        """
        canvas = image_input.copy().convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        w, h = canvas.size
        margin = int(w * 0.08)  # 8% safety margin
        content_width = w - (margin * 2)

        author_name = self.brand_cfg.get("name", "Anshu Pal")
        handle = self.brand_cfg.get("handle", "@rexmarchen")
        flagship = self.brand_cfg.get("flagship", "REXION")

        if layout_type == "photo-only":
            # Just subtle corner watermark / brand tag
            tag_font = self.get_font("body", 22)
            tag_text = f"{flagship} // {handle}"
            bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            px = w - margin - tw - 20
            py = h - margin - th - 10
            # Pill card
            draw.rounded_rectangle([px - 14, py - 6, px + tw + 14, py + th + 6], radius=8, fill=(15, 18, 24, 180))
            draw.text((px, py), tag_text, font=tag_font, fill=self.c_text_light + (240,))

        elif layout_type == "headline-on-photo":
            # Dynamic headline font size based on image width
            h_size = int(w * 0.052)  # ~53px for 1024 width
            heading_font = self.get_font("heading", h_size)
            lines = self.wrap_text(headline, heading_font, content_width, draw)

            line_height = int(h_size * 1.25)
            total_text_h = line_height * len(lines)

            # Determine Y start
            if text_zone == "top":
                start_y = margin + 50
            else:
                start_y = h - margin - total_text_h - 100

            # Pill backing card for pristine contrast & legibility
            card_pad = 24
            card_box = [
                margin - card_pad,
                start_y - card_pad,
                w - margin + card_pad,
                start_y + total_text_h + card_pad,
            ]
            draw.rounded_rectangle(card_box, radius=16, fill=(15, 18, 24, 215))

            # Brand badge
            badge_font = self.get_font("body", 18)
            badge_text = f"{flagship} // ENGINEERING"
            draw.text((margin, start_y - 20), badge_text, font=badge_font, fill=self.c_secondary + (255,))

            # Render headline lines
            curr_y = start_y + 12
            for line in lines:
                draw.text((margin, curr_y), line, font=heading_font, fill=self.c_text_light + (255,))
                curr_y += line_height

            # Footer handle
            footer_font = self.get_font("body", 20)
            footer_text = f"{author_name} • {handle}"
            draw.text((margin, h - margin - 30), footer_text, font=footer_font, fill=self.c_text_light + (220,))

        elif layout_type == "quote-card":
            # Elegant center card
            card_w = content_width
            card_h = int(h * 0.42)
            card_x = margin
            card_y = int((h - card_h) / 2)

            # Warm matte card surface
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=20, fill=self.c_bg_light + (245,))
            draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=20, outline=self.c_primary + (180,), width=3)

            # Decorative left accent bar
            draw.rounded_rectangle([card_x + 20, card_y + 30, card_x + 28, card_y + card_h - 30], radius=4, fill=self.c_primary + (255,))

            h_size = int(w * 0.046)
            heading_font = self.get_font("heading", h_size)
            lines = self.wrap_text(f'"{headline}"', heading_font, card_w - 90, draw)

            line_height = int(h_size * 1.3)
            curr_y = card_y + 45
            for line in lines:
                draw.text((card_x + 50, curr_y), line, font=heading_font, fill=self.c_text_dark + (255,))
                curr_y += line_height

            # Attribution
            body_font = self.get_font("body", 22)
            draw.text((card_x + 50, card_y + card_h - 55), f"— {author_name}", font=body_font, fill=self.c_accent + (255,))
            draw.text((card_x + card_w - 140, card_y + card_h - 55), flagship, font=body_font, fill=self.c_primary + (255,))

        final_composite = Image.alpha_composite(canvas, overlay)
        return final_composite.convert("RGB")
