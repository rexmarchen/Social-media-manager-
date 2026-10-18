"""
Reference Poster Engine for REXION
---------------------------------
Generates production-grade, high-fidelity graphic design posters matching the exact visual
formats from the user's reference dataset:
1. cutting_mat_stack (Orange cutting mat, tilted papers, paper clips, pastel blocks, grotesque sans)
2. mustard_retro_poster (Mustard yellow, fold lines, retro PC, editorial serif, witty margin annotations)
3. cobalt_blueprint (Electric cobalt blue, white blueprint frame, wireframe globe, CRT monitor, pipeline boxes)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

log = logging.getLogger("reference_poster_engine")

ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT_DIR / "generated_images"
GENERATED_DIR.mkdir(exist_ok=True)
REF_DIR = ROOT_DIR / "reference_images" / "gdrive_dataset"


def get_font(size: int, bold: bool = False, serif: bool = False, mono: bool = False) -> ImageFont.ImageFont:
    """Loads system fonts on Windows/Linux or falls back gracefully."""
    candidates = []
    if mono:
        candidates = ["consola.ttf", "consolab.ttf" if bold else "consola.ttf", "cour.ttf", "courbd.ttf", "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"]
    elif serif:
        candidates = ["georgia.ttf", "georgiab.ttf" if bold else "georgia.ttf", "times.ttf", "timesbd.ttf", "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"]
    elif bold:
        candidates = ["impact.ttf", "arialbd.ttf", "segoeuib.ttf", "trebucbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    else:
        candidates = ["arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]

    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class ReferencePosterEngine:
    """
    Renders posters faithfully replicating the 3 core reference styles with dynamic text.
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or GENERATED_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        archetype: str = "cutting_mat_stack",
        headline_lines: Optional[List[str]] = None,
        tag: Optional[str] = None,
        subtitle: Optional[str] = None,
        bullet_points: Optional[List[str]] = None,
        cta: Optional[str] = None,
        author: str = "Anshu Pal",
        handle: str = "@rexmarchen",
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        Main entry point for generating a poster adhering strictly to reference design.
        """
        archetype = archetype.lower().strip()
        if archetype not in ("cutting_mat_stack", "mustard_retro_poster", "cobalt_blueprint"):
            archetype = "cutting_mat_stack"

        out_name = output_filename or f"rexion_{archetype}_{random.randint(1000, 9999)}.jpg"
        out_path = self.output_dir / out_name

        if archetype == "cutting_mat_stack":
            return self._render_cutting_mat(
                out_path=out_path,
                headline_lines=headline_lines,
                tag=tag,
                subtitle=subtitle,
                cta=cta,
                handle=handle,
            )
        elif archetype == "mustard_retro_poster":
            return self._render_mustard_poster(
                out_path=out_path,
                headline_lines=headline_lines,
                tag=tag,
                bullet_points=bullet_points,
                author=author,
                handle=handle,
            )
        else:
            return self._render_cobalt_blueprint(
                out_path=out_path,
                headline_lines=headline_lines,
                tag=tag,
                subtitle=subtitle,
                bullet_points=bullet_points,
                author=author,
                handle=handle,
            )

    # =========================================================================
    # ARCHETYPE 1: CUTTING MAT & LAYERED CREAM DOCUMENT STACK
    # =========================================================================
    def _render_cutting_mat(
        self,
        out_path: Path,
        headline_lines: Optional[List[str]],
        tag: Optional[str],
        subtitle: Optional[str],
        cta: Optional[str],
        handle: str,
    ) -> Path:
        W, H = 1080, 1350
        # Vibrant orange cutting mat (#E85A18)
        canvas = Image.new("RGB", (W, H), (232, 90, 24))
        draw = ImageDraw.Draw(canvas)

        # 1. Grid pattern
        grid_color = (255, 120, 60)
        grid_step = 36
        for x in range(0, W, grid_step):
            draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
        for y in range(0, H, grid_step):
            draw.line([(0, y), (W, y)], fill=grid_color, width=1)

        # Top handle text
        top_font = get_font(26, bold=True)
        h_box = draw.textbbox((0, 0), handle, font=top_font)
        draw.text(((W - (h_box[2] - h_box[0])) // 2, 85), handle, font=top_font, fill=(255, 255, 255))

        # 2. Backing paper drop shadow & tilted under-papers
        paper_w, paper_h = 760, 960
        paper_x, paper_y = (W - paper_w) // 2, 175

        # Base drop shadow
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rectangle([paper_x + 12, paper_y + 16, paper_x + paper_w + 12, paper_y + paper_h + 16], fill=(0, 0, 0, 95))
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
        draw = ImageDraw.Draw(canvas)

        # Under-paper 1 (tilted left 2.5 degrees)
        under_paper1 = Image.new("RGBA", (paper_w + 40, paper_h + 40), (0, 0, 0, 0))
        up1_draw = ImageDraw.Draw(under_paper1)
        up1_draw.rectangle([10, 10, paper_w + 10, paper_h + 10], fill=(245, 245, 247), outline=(210, 210, 215), width=1)
        up1_rot = under_paper1.rotate(2.5, resample=Image.Resampling.BICUBIC, expand=True)
        canvas.paste(up1_rot, (paper_x - 30, paper_y - 20), up1_rot)

        # Under-paper 2 (tilted right -2.0 degrees)
        under_paper2 = Image.new("RGBA", (paper_w + 40, paper_h + 40), (0, 0, 0, 0))
        up2_draw = ImageDraw.Draw(under_paper2)
        up2_draw.rectangle([10, 10, paper_w + 10, paper_h + 10], fill=(248, 248, 250), outline=(220, 220, 225), width=1)
        up2_rot = under_paper2.rotate(-2.0, resample=Image.Resampling.BICUBIC, expand=True)
        canvas.paste(up2_rot, (paper_x - 10, paper_y - 15), up2_rot)

        # Foreground warm textured cream paper
        paper = Image.new("RGB", (paper_w, paper_h), (250, 248, 245))
        p_draw = ImageDraw.Draw(paper)
        p_draw.rectangle([0, 0, paper_w - 1, paper_h - 1], outline=(225, 220, 215), width=1)

        # Top-left realistic paper clip
        clip_x, clip_y = 60, 40
        p_draw.arc([clip_x, clip_y, clip_x + 36, clip_y + 80], 180, 0, fill=(90, 90, 95), width=4)
        p_draw.line([clip_x, clip_y + 40, clip_x, clip_y + 110], fill=(90, 90, 95), width=4)
        p_draw.line([clip_x + 36, clip_y + 40, clip_x + 36, clip_y + 120], fill=(90, 90, 95), width=4)
        p_draw.arc([clip_x, clip_y + 90, clip_x + 36, clip_y + 130], 0, 180, fill=(90, 90, 95), width=4)

        # Pill Tag / Category
        tag_text = tag or "Before You Apply to Another Job..."
        callout_font = get_font(18, bold=True)
        c_bbox = p_draw.textbbox((0, 0), tag_text, font=callout_font)
        cw = (c_bbox[2] - c_bbox[0]) + 36
        ch = (c_bbox[3] - c_bbox[1]) + 16
        cx, cy = 90, 150
        p_draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=ch // 2, outline=(232, 90, 24), fill=(255, 255, 255), width=2)
        p_draw.text((cx + 18, cy + 7), tag_text, font=callout_font, fill=(232, 90, 24))

        # Headline
        lines = headline_lines or ["I built", "REXION", "to automate", "the grind."]
        
        # Calculate optimal font size so all lines fit within paper_w - 190
        max_allowed_w = paper_w - 190
        h_font_size = 96
        while h_font_size > 48:
            test_font = get_font(h_font_size, bold=True)
            fits = True
            for line in lines[:4]:
                bb = p_draw.textbbox((0, 0), line, font=test_font)
                if (bb[2] - bb[0]) > max_allowed_w:
                    fits = False
                    break
            if fits:
                break
            h_font_size -= 4

        h_font = get_font(h_font_size, bold=True)
        line_height = int(h_font_size * 1.15)
        y_cursor = 215

        # Compute line boxes for pastel blocks
        rendered_lines = lines[:4]
        line_boxes = []
        for i, line in enumerate(rendered_lines):
            x_pos = 160 if i == 0 and len(rendered_lines) > 1 else 95
            bb = p_draw.textbbox((0, 0), line, font=h_font)
            lw = bb[2] - bb[0]
            lh = bb[3] - bb[1]
            line_boxes.append((line, x_pos, y_cursor, lw, lh))
            y_cursor += line_height

        # Draw pastel highlight blocks behind line 0 and line 2 (Alex Joseph style)
        if len(line_boxes) >= 1:
            l0_line, l0_x, l0_y, l0_w, l0_h = line_boxes[0]
            p_draw.rectangle([l0_x - 14, l0_y - 6, l0_x + l0_w + 18, l0_y + l0_h + 12], fill=(208, 198, 242))  # Lavender
        if len(line_boxes) >= 3:
            l2_line, l2_x, l2_y, l2_w, l2_h = line_boxes[2]
            p_draw.rectangle([l2_x - 14, l2_y - 6, l2_x + l2_w + 18, l2_y + l2_h + 12], fill=(252, 192, 168))  # Peach

        # Draw headline text on top of pastel blocks
        for line, x_pos, y_pos, lw, lh in line_boxes:
            p_draw.text((x_pos, y_pos), line, font=h_font, fill=(26, 26, 28))

        # Orange folder icon sticker in top-right
        folder_x, folder_y = paper_w - 170, 260
        p_draw.polygon(
            [(folder_x, folder_y + 12), (folder_x + 30, folder_y + 12), (folder_x + 42, folder_y + 24), (folder_x + 95, folder_y + 24), (folder_x + 95, folder_y + 80), (folder_x, folder_y + 80)],
            fill=(242, 100, 32),
        )
        p_draw.rectangle([folder_x, folder_y + 24, folder_x + 95, folder_y + 80], fill=(255, 115, 40))

        # Subtitle with word wrapping
        sub_text = subtitle or "Job hunting without automation is just noise. Let's fix that."
        sub_font = get_font(22, serif=True)
        sub_words = sub_text.split()
        sub_lines = []
        cur_line = []
        for w in sub_words:
            test_line = " ".join(cur_line + [w])
            sbb = p_draw.textbbox((0, 0), test_line, font=sub_font)
            if (sbb[2] - sbb[0]) > (paper_w - 200) and cur_line:
                sub_lines.append(" ".join(cur_line))
                cur_line = [w]
            else:
                cur_line.append(w)
        if cur_line:
            sub_lines.append(" ".join(cur_line))

        sub_y = max(y_cursor + 20, 680)
        for s_line in sub_lines[:3]:
            p_draw.text((105, sub_y), s_line, font=sub_font, fill=(75, 75, 80))
            sub_y += 34

        # Masking tape strip CTA
        cta_text = cta or "Swipe to see the AI architecture behind REXION ->"
        tape_x, tape_y = 105, max(sub_y + 25, 775)
        tape_w, tape_h = 550, 52
        tape_overlay = Image.new("RGBA", (paper_w, paper_h), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(tape_overlay)
        t_draw.rectangle([tape_x, tape_y, tape_x + tape_w, tape_y + tape_h], fill=(225, 218, 205, 215))
        paper = Image.alpha_composite(paper.convert("RGBA"), tape_overlay).convert("RGB")
        p_draw = ImageDraw.Draw(paper)
        tape_font = get_font(18, serif=True)
        p_draw.text((tape_x + 24, tape_y + 14), cta_text, font=tape_font, fill=(60, 55, 50))

        # Paste paper onto canvas
        canvas.paste(paper, (paper_x, paper_y))
        draw = ImageDraw.Draw(canvas)

        # Metallic binder clip on right edge
        clip_rx, clip_ry = paper_x + paper_w - 25, paper_y + 440
        draw.rounded_rectangle([clip_rx, clip_ry, clip_rx + 55, clip_ry + 115], radius=6, fill=(195, 195, 200), outline=(130, 130, 135), width=2)
        draw.arc([clip_rx + 25, clip_ry - 30, clip_rx + 90, clip_ry + 55], 90, 270, fill=(110, 110, 115), width=4)
        draw.arc([clip_rx + 25, clip_ry + 60, clip_rx + 90, clip_ry + 145], 90, 270, fill=(110, 110, 115), width=4)

        # Bottom footer
        foot_font = get_font(26, bold=True)
        foot_text = "REXION System Architecture 2026"
        f_bbox = draw.textbbox((0, 0), foot_text, font=foot_font)
        draw.text(((W - (f_bbox[2] - f_bbox[0])) // 2, H - 90), foot_text, font=foot_font, fill=(255, 255, 255))

        canvas.save(out_path, "JPEG", quality=95)
        return out_path

    # =========================================================================
    # ARCHETYPE 2: MUSTARD YELLOW RETRO-COMPUTING POSTER
    # =========================================================================
    def _render_mustard_poster(
        self,
        out_path: Path,
        headline_lines: Optional[List[str]],
        tag: Optional[str],
        bullet_points: Optional[List[str]],
        author: str,
        handle: str,
    ) -> Path:
        W, H = 1080, 1350
        # Warm mustard yellow (#F5BA04)
        canvas = Image.new("RGB", (W, H), (245, 186, 4))
        draw = ImageDraw.Draw(canvas)

        # 1. Subtle Paper Fold Creases
        h_fold_y = H // 2
        draw.line([(0, h_fold_y - 1), (W, h_fold_y - 1)], fill=(215, 160, 0), width=1)
        draw.line([(0, h_fold_y), (W, h_fold_y)], fill=(190, 140, 0), width=1)
        draw.line([(0, h_fold_y + 1), (W, h_fold_y + 1)], fill=(255, 210, 60), width=1)

        v_fold_x = W // 2
        draw.line([(v_fold_x - 1, 0), (v_fold_x - 1, H)], fill=(215, 160, 0), width=1)
        draw.line([(v_fold_x, 0), (v_fold_x, H)], fill=(190, 140, 0), width=1)
        draw.line([(v_fold_x + 1, 0), (v_fold_x + 1, H)], fill=(255, 210, 60), width=1)

        # 2. Top thin outline pill box
        pill_font = get_font(20, bold=False)
        pill_text = tag or "intelligent job discovery"
        pb = draw.textbbox((0, 0), pill_text, font=pill_font)
        pw, ph = pb[2] - pb[0] + 36, pb[3] - pb[1] + 18
        px = (W - pw) // 2
        py = 180
        draw.rectangle([px, py, px + pw, py + ph], outline=(20, 20, 22), width=2)
        draw.text((px + 18, py + 8), pill_text, font=pill_font, fill=(20, 20, 22))

        # 3. High-contrast display serif headline
        lines = headline_lines or [
            "Ever since I built REXION",
            "I knew Job Hunting shouldn't be",
            "a full-time manual job",
        ]
        title_font = get_font(56, bold=True, serif=True)
        y_start = 250
        for i, line in enumerate(lines[:3]):
            bbox = draw.textbbox((0, 0), line, font=title_font)
            lw = bbox[2] - bbox[0]
            draw.text(((W - lw) // 2, y_start + (i * 75)), line, font=title_font, fill=(20, 20, 22))

        # 4. Centered retro beige PC setup (cutout from reference if exists)
        ref_pc_file = REF_DIR / "9941495476bd0631eea5bd2497dd461d.jpg"
        if ref_pc_file.exists():
            with Image.open(ref_pc_file) as ref_img:
                rw, rh = ref_img.size
                crop_box = (int(rw * 0.23), int(rh * 0.35), int(rw * 0.77), int(rh * 0.68))
                pc_crop = ref_img.crop(crop_box).convert("RGB")
                pc_draw = ImageDraw.Draw(pc_crop)
                mustard = (245, 186, 4)
                pc_draw.rectangle([0, 0, 95, 200], fill=mustard)
                pc_draw.rectangle([pc_crop.width - 100, 0, pc_crop.width, 240], fill=mustard)

                pc_w = 540
                pc_h = int(pc_w * (pc_crop.height / pc_crop.width))
                pc_resized = pc_crop.resize((pc_w, pc_h), Image.Resampling.LANCZOS)
                canvas.paste(pc_resized, ((W - pc_w) // 2, 530))
        else:
            # Fallback graphic representation of retro PC
            pc_draw_box = [(W - 400) // 2, 540, (W + 400) // 2, 860]
            draw.rectangle(pc_draw_box, fill=(230, 225, 210), outline=(50, 50, 55), width=3)
            # Screen
            draw.rectangle([pc_draw_box[0] + 40, pc_draw_box[1] + 30, pc_draw_box[2] - 40, pc_draw_box[3] - 80], fill=(24, 50, 215), outline=(50, 50, 55), width=2)
            draw.text((pc_draw_box[0] + 60, pc_draw_box[1] + 60), "C:\\> REXION_AGENT --LIVE\nOK.\n[MATCHING ACTIVE]", font=get_font(20, mono=True), fill=(255, 255, 255))

        # 5. Witty side annotations
        side_font = get_font(18, bold=False)
        draw.text((70, 520), "manual applying takes hours\nautomated matching takes >>>", font=side_font, fill=(20, 20, 22))
        draw.text((W - 270, 570), "it's all about deterministic\nATS scoring //", font=side_font, fill=(20, 20, 22))

        # 6. Bottom rhythmic insights
        bullets = bullet_points or [
            "Always indexing listings, filtering every single company",
            "Smart resume parser active at least twice a day",
            "Strictly low-latency architecture, zero unindexed scans",
        ]
        insight_font = get_font(21, serif=True)
        y_b = 1020
        for b in bullets[:3]:
            bbox = draw.textbbox((0, 0), b, font=insight_font)
            bw = bbox[2] - bbox[0]
            draw.text(((W - bw) // 2, y_b), b, font=insight_font, fill=(20, 20, 22))
            y_b += 35

        # 7. Branding Signature
        brand_logo_font = get_font(34, bold=True)
        draw.text((280, 1200), "REXION", font=brand_logo_font, fill=(20, 20, 22))
        foot_font = get_font(18, bold=False)
        foot_txt = f"get in touch ->\n{author.lower().replace(' ', '.')} • github.com/{handle.lstrip('@')}"
        draw.text((450, 1205), foot_txt, font=foot_font, fill=(20, 20, 22))

        canvas.save(out_path, "JPEG", quality=95)
        return out_path

    # =========================================================================
    # ARCHETYPE 3: COBALT BLUEPRINT INFOGRAPHIC COLLAGE
    # =========================================================================
    def _render_cobalt_blueprint(
        self,
        out_path: Path,
        headline_lines: Optional[List[str]],
        tag: Optional[str],
        subtitle: Optional[str],
        bullet_points: Optional[List[str]],
        author: str,
        handle: str,
    ) -> Path:
        W, H = 1080, 1350
        # Electric Cobalt Blue (#1832D7)
        canvas = Image.new("RGB", (W, H), (24, 50, 215))
        draw = ImageDraw.Draw(canvas)

        # Subtle distressed speckles (low contrast, authentic blueprint paper grain)
        rng = random.Random(42)
        for _ in range(400):
            sx = rng.randint(35, W - 35)
            sy = rng.randint(35, H - 35)
            s_len = rng.randint(1, 3)
            draw.line([(sx, sy), (sx + s_len, sy)], fill=(35, 70, 230), width=1)

        # 1. White border frame (2px solid white blueprint margin)
        margin = 35
        draw.rectangle([margin, margin, W - margin, H - margin], outline=(255, 255, 255), width=2)

        # 2. Headline across top (Auto-scaling to never clip with globe)
        lines = headline_lines or ["REXION", "PIPELINE"]
        max_title_w = W - 320
        title_size = 100
        while title_size > 60:
            test_f = get_font(title_size, bold=True)
            fits = True
            for l in lines[:2]:
                bb = draw.textbbox((0, 0), l, font=test_f)
                if (bb[2] - bb[0]) > max_title_w:
                    fits = False
                    break
            if fits:
                break
            title_size -= 4

        title_font = get_font(title_size, bold=True)
        line_h = int(title_size * 1.1)
        draw.text((55, 50), lines[0], font=title_font, fill=(255, 255, 255))
        if len(lines) > 1:
            draw.text((55, 50 + line_h), lines[1], font=title_font, fill=(255, 255, 255))

        # Slanted hazard stripes top-right
        for i in range(7):
            bx = 740 + (i * 22)
            draw.polygon([(bx, 60), (bx + 14, 60), (bx + 4, 75), (bx - 10, 75)], fill=(255, 255, 255))

        # 3D wireframe globe top right
        gw_center = (860, 140)
        for r in range(15, 65, 15):
            draw.ellipse([gw_center[0] - r, gw_center[1] - r, gw_center[0] + r, gw_center[1] + r], outline=(255, 255, 255), width=1)
        draw.ellipse([gw_center[0] - 60, gw_center[1] - 25, gw_center[0] + 60, gw_center[1] + 25], outline=(255, 255, 255), width=1)
        draw.ellipse([gw_center[0] - 25, gw_center[1] - 60, gw_center[0] + 25, gw_center[1] + 60], outline=(255, 255, 255), width=1)

        # 3. Cutout CRT monitor & hardware collage (100% clean crop, zero residual letters, soft feather)
        cw_dest = 440
        ref_os_file = REF_DIR / "864b230f28ed5658ac59d54c4ada307e.jpg"
        if ref_os_file.exists():
            with Image.open(ref_os_file) as ref_img:
                rw, rh = ref_img.size
                # Precise crop: x=440 (past SYSTEMS text), y=175 (below OPERATING text)
                crop_box = (440, 175, rw - 10, int(rh * 0.84))
                collage_crop = ref_img.crop(crop_box).convert("RGBA")

                ch_dest = int(cw_dest * (collage_crop.height / collage_crop.width))
                collage_resized = collage_crop.resize((cw_dest, ch_dest), Image.Resampling.LANCZOS)

                # Create smooth alpha feather mask for left, top, and bottom edges
                mask = Image.new("L", (cw_dest, ch_dest), 255)
                m_draw = ImageDraw.Draw(mask)

                # Feather left edge over 40 pixels for seamless backdrop blend
                for x in range(40):
                    alpha = int((x / 40.0) * 255)
                    m_draw.line([(x, 0), (x, ch_dest)], fill=alpha)

                # Feather top edge over 30 pixels
                for y in range(30):
                    alpha = int((y / 30.0) * 255)
                    for x in range(cw_dest):
                        cur_a = mask.getpixel((x, y))
                        mask.putpixel((x, y), min(cur_a, alpha))

                # Feather bottom edge over 40 pixels
                for dy in range(40):
                    y = ch_dest - 1 - dy
                    alpha = int((dy / 40.0) * 255)
                    for x in range(cw_dest):
                        cur_a = mask.getpixel((x, y))
                        mask.putpixel((x, y), min(cur_a, alpha))

                collage_resized.putalpha(mask)
                canvas.paste(collage_resized, (W - cw_dest - 35, 290), collage_resized)

        # 4. Technical explanation block with strict word wrapping
        draw = ImageDraw.Draw(canvas)
        body_font = get_font(18, bold=True)
        body_small = get_font(15, bold=False)
        lx = 65
        max_col_w = 410

        def wrap_lines(text: str, font: ImageFont.ImageFont, max_w: int) -> List[str]:
            res = []
            for raw_chunk in text.split("\n"):
                words = raw_chunk.split()
                if not words:
                    res.append("")
                    continue
                cur = []
                for w in words:
                    cand = " ".join(cur + [w])
                    bb = draw.textbbox((0, 0), cand, font=font)
                    if (bb[2] - bb[0]) > max_w and cur:
                        res.append(" ".join(cur))
                        cur = [w]
                    else:
                        cur.append(w)
                if cur:
                    res.append(" ".join(cur))
            return res

        # Tag intro
        intro_text = tag or "///////\nAN AI PIPELINE THAT ACTS AS A BRIDGE\nBETWEEN DISPERSED JOB BOARDS\nAND RELEVANT APPLICANTS."
        intro_wrapped = wrap_lines(intro_text, body_font, max_col_w)
        y_text = 330
        for l in intro_wrapped:
            draw.text((lx, y_text), l, font=body_font, fill=(255, 255, 255))
            y_text += 26

        y_text += 25
        section_title = f"OVERVIEW // {lines[0].upper()}" if len(lines) > 0 else "SYSTEM ARCHITECTURE:"
        draw.text((lx, y_text), section_title, font=get_font(21, bold=True), fill=(255, 255, 255))
        y_text += 32

        expl_text = subtitle or "REXION IS AN AUTOMATED SYSTEM PLATFORM THAT CRAWLS, PARSES, AND SCORES JOB OPENINGS IN REAL-TIME, MATCHING CANDIDATES DETERMINISTICALLY."
        expl_wrapped = wrap_lines(expl_text, body_small, max_col_w)
        for l in expl_wrapped:
            draw.text((lx, y_text), l, font=body_small, fill=(255, 255, 255))
            y_text += 22

        y_text += 30
        draw.text((lx, y_text), "CORE CAPABILITIES", font=get_font(21, bold=True), fill=(255, 255, 255))
        y_text += 32

        default_caps = [
            "• MULTI-SOURCE INGESTION",
            "• REAL-TIME DEDUPLICATION",
            "• ATS KEYWORD SCORING",
            "• VECTOR RESUME RETRIEVAL",
            "• ONE-CLICK APPLICATION FLOW"
        ]
        for cap in default_caps:
            draw.text((lx, y_text), cap, font=body_small, fill=(255, 255, 255))
            y_text += 22

        # 5. System Architecture Pipeline Boxes (High contrast solid blue fill)
        arch_y = 970
        draw.text((lx, arch_y), "SYSTEM ARCHITECTURE PIPELINE", font=get_font(22, bold=True), fill=(255, 255, 255))

        box_w, box_h = 425, 42
        boxes = bullet_points or [
            "1. DISTRIBUTED DATA SCRAPERS",
            "2. SEMANTIC DEDUPLICATION (SHA-256)",
            "3. LLM RESUME PARSER & ATS FIT SCORE",
            "4. POSTGRESQL / VECTOR STORE INDEX",
        ]
        for i, b_text in enumerate(boxes[:4]):
            by = arch_y + 36 + (i * 48)
            draw.rectangle([lx, by, lx + box_w, by + box_h], fill=(16, 36, 175), outline=(255, 255, 255), width=1)
            draw.text((lx + 15, by + 12), b_text, font=get_font(15, bold=True), fill=(255, 255, 255))

        # Bottom Right Quote Box (Solid fill to cleanly overlay hardware without clashes)
        rx = 520
        draw.rectangle([rx, arch_y + 36, W - 55, arch_y + 228], fill=(16, 36, 175), outline=(255, 255, 255), width=1)
        q_text = "WITHOUT AUTOMATION, JOB SEARCH IS JUST A\nREPETITIVE CHORE. WITH REXION, IT BECOMES\nA PREDICTABLE, HIGH-THROUGHPUT SYSTEM."
        draw.text((rx + 20, arch_y + 55), q_text, font=get_font(15, bold=True), fill=(255, 255, 255))
        draw.line([(rx + 20, arch_y + 120), (W - 75, arch_y + 120)], fill=(255, 255, 255), width=1)
        draw.text((rx + 20, arch_y + 135), f"CREATOR: {author.upper()}\nFLAGSHIP: REXION.AI", font=get_font(15, bold=True), fill=(255, 255, 255))
        draw.text((rx + 270, arch_y + 135), f"{handle.upper()}\n2026 EDITION", font=get_font(15, bold=True), fill=(255, 255, 255))

        canvas.save(out_path, "JPEG", quality=95)
        return out_path


def format_title_to_lines(title: str, max_lines: int = 4) -> List[str]:
    """Splits a long topic or title into punchy poster headline chunks."""
    words = title.strip().split()
    if len(words) <= max_lines:
        return words
    # Group words into 3-4 chunks
    chunk_size = math.ceil(len(words) / max_lines)
    lines = []
    for i in range(0, len(words), chunk_size):
        lines.append(" ".join(words[i : i + chunk_size]))
    return lines[:max_lines]


def main():
    parser = argparse.ArgumentParser(description="Reference Poster Engine CLI")
    parser.add_argument("--archetype", default="cutting_mat_stack", choices=["cutting_mat_stack", "mustard_retro_poster", "cobalt_blueprint"])
    parser.add_argument("--title", default=None)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--subtitle", default=None)
    parser.add_argument("--cta", default=None)
    parser.add_argument("--out-file", default=None)
    args = parser.parse_args()

    engine = ReferencePosterEngine()
    lines = None
    if args.title:
        lines = [x.strip() for x in args.title.split(",") if x.strip()]
        if len(lines) == 1:
            lines = format_title_to_lines(lines[0])

    out = engine.generate(
        archetype=args.archetype,
        headline_lines=lines,
        tag=args.tag,
        subtitle=args.subtitle,
        cta=args.cta,
        output_filename=args.out_file,
    )
    print(str(out))


if __name__ == "__main__":
    main()
