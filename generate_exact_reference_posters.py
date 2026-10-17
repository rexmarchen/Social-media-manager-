"""
High-Fidelity Graphic Design Poster Engine for REXION
Faithfully recreates the exact graphic design poster formats from the user's reference dataset:
1. Design 1: Cutting Mat Paper Stack (Alex Joseph / Branding style)
2. Design 2: Mustard Yellow Folded Poster (Apins / Retro Tech style)
3. Design 3: Cobalt OS Blueprint Poster (Operating Systems collage style)
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

OUTPUT_DIR = Path("generated_images")
OUTPUT_DIR.mkdir(exist_ok=True)
REF_DIR = Path("reference_images/gdrive_dataset")


def get_font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.ImageFont:
    candidate_fonts = []
    if serif:
        candidate_fonts = ["georgia.ttf", "times.ttf", "timesbd.ttf" if bold else "times.ttf", "segoeui.ttf"]
    elif bold:
        candidate_fonts = ["impact.ttf", "arialbd.ttf", "segoeuib.ttf", "trebucbd.ttf", "arial.ttf"]
    else:
        candidate_fonts = ["arial.ttf", "segoeui.ttf", "calibri.ttf"]

    for name in candidate_fonts:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ==============================================================================
# DESIGN 1: Cutting Mat & Pinned Document Stack (Ref: 0a56c216..., 0623fb1c...)
# ==============================================================================
def create_design_1_cutting_mat_stack(out_path: Path) -> Path:
    W, H = 1080, 1350  # 4:5 Instagram/LinkedIn vertical portrait (exact reference format)
    canvas = Image.new("RGB", (W, H), (232, 90, 24))  # Rich vibrant orange (#E85A18)
    draw = ImageDraw.Draw(canvas)

    # 1. Grid pattern on cutting mat
    grid_color = (255, 120, 60)
    grid_step = 36
    for x in range(0, W, grid_step):
        draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
    for y in range(0, H, grid_step):
        draw.line([(0, y), (W, y)], fill=grid_color, width=1)

    # Top handle
    top_font = get_font(26, bold=True)
    handle_text = "@rexmarchen"
    bbox = draw.textbbox((0, 0), handle_text, font=top_font)
    draw.text(((W - (bbox[2] - bbox[0])) // 2, 85), handle_text, font=top_font, fill=(255, 255, 255))

    # 2. Backing paper shadow & tilted background papers
    paper_w, paper_h = 760, 960
    paper_x, paper_y = (W - paper_w) // 2, 175

    # Base drop shadow
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rectangle([paper_x + 12, paper_y + 16, paper_x + paper_w + 12, paper_y + paper_h + 16], fill=(0, 0, 0, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Under-paper 1 (tilted left)
    under_paper1 = Image.new("RGBA", (paper_w + 40, paper_h + 40), (0, 0, 0, 0))
    up1_draw = ImageDraw.Draw(under_paper1)
    up1_draw.rectangle([10, 10, paper_w + 10, paper_h + 10], fill=(245, 245, 247), outline=(210, 210, 215), width=1)
    up1_rot = under_paper1.rotate(2.5, resample=Image.Resampling.BICUBIC, expand=True)
    canvas.paste(up1_rot, (paper_x - 30, paper_y - 20), up1_rot)

    # Under-paper 2 (tilted right)
    under_paper2 = Image.new("RGBA", (paper_w + 40, paper_h + 40), (0, 0, 0, 0))
    up2_draw = ImageDraw.Draw(under_paper2)
    up2_draw.rectangle([10, 10, paper_w + 10, paper_h + 10], fill=(248, 248, 250), outline=(220, 220, 225), width=1)
    up2_rot = under_paper2.rotate(-2.0, resample=Image.Resampling.BICUBIC, expand=True)
    canvas.paste(up2_rot, (paper_x - 10, paper_y - 15), up2_rot)

    # Main foreground paper (Warm textured cream paper)
    paper = Image.new("RGB", (paper_w, paper_h), (250, 248, 245))
    p_draw = ImageDraw.Draw(paper)
    p_draw.rectangle([0, 0, paper_w - 1, paper_h - 1], outline=(225, 220, 215), width=1)

    # Paper clip in top-left
    clip_x, clip_y = 60, 40
    p_draw.arc([clip_x, clip_y, clip_x + 36, clip_y + 80], 180, 0, fill=(90, 90, 95), width=4)
    p_draw.line([clip_x, clip_y + 40, clip_x, clip_y + 110], fill=(90, 90, 95), width=4)
    p_draw.line([clip_x + 36, clip_y + 40, clip_x + 36, clip_y + 120], fill=(90, 90, 95), width=4)
    p_draw.arc([clip_x, clip_y + 90, clip_x + 36, clip_y + 130], 0, 180, fill=(90, 90, 95), width=4)

    # Callout pill: (Before You Apply to Another Job...)
    callout_font = get_font(18, bold=True)
    callout_text = "Before You Apply to Another Job..."
    c_bbox = p_draw.textbbox((0, 0), callout_text, font=callout_font)
    cw = (c_bbox[2] - c_bbox[0]) + 36
    ch = (c_bbox[3] - c_bbox[1]) + 16
    cx, cy = 90, 150
    p_draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=ch//2, outline=(232, 90, 24), fill=(255, 255, 255), width=2)
    p_draw.text((cx + 18, cy + 7), callout_text, font=callout_font, fill=(232, 90, 24))

    # Pastel Block 1 for "REXION"
    block1_x, block1_y = 190, 220
    p_draw.rectangle([block1_x, block1_y, block1_x + 360, block1_y + 105], fill=(208, 198, 242))  # Lavender block
    # Pastel Block 2 for "system"
    p_draw.rectangle([block1_x - 100, block1_y + 240, block1_x + 460, block1_y + 360], fill=(252, 192, 168))  # Peach block

    # Main Headline (Massive condensed typography)
    h_font = get_font(105, bold=True)
    p_draw.text((195, 215), "I built", font=h_font, fill=(26, 26, 28))
    p_draw.text((95, 325), "REXION", font=h_font, fill=(26, 26, 28))
    p_draw.text((95, 440), "to automate", font=h_font, fill=(26, 26, 28))
    p_draw.text((95, 555), "the grind.", font=h_font, fill=(26, 26, 28))

    # Orange folder sticker icon in top right
    folder_x, folder_y = 530, 280
    p_draw.polygon([(folder_x, folder_y + 12), (folder_x + 30, folder_y + 12), (folder_x + 42, folder_y + 24), (folder_x + 95, folder_y + 24), (folder_x + 95, folder_y + 80), (folder_x, folder_y + 80)], fill=(242, 100, 32))
    p_draw.rectangle([folder_x, folder_y + 24, folder_x + 95, folder_y + 80], fill=(255, 115, 40))

    # Subtitle
    sub_font = get_font(23, serif=True)
    p_draw.text((110, 690), "Job hunting without automation is just noise. Let's fix that.", font=sub_font, fill=(75, 75, 80))

    # Masking tape strip CTA
    tape_x, tape_y = 120, 770
    tape_w, tape_h = 510, 52
    tape_overlay = Image.new("RGBA", (paper_w, paper_h), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(tape_overlay)
    t_draw.rectangle([tape_x, tape_y, tape_x + tape_w, tape_y + tape_h], fill=(225, 218, 205, 215))
    paper = Image.alpha_composite(paper.convert("RGBA"), tape_overlay).convert("RGB")
    p_draw = ImageDraw.Draw(paper)
    tape_font = get_font(18, serif=True)
    p_draw.text((tape_x + 28, tape_y + 14), "Swipe to see the AI architecture behind REXION ->", font=tape_font, fill=(60, 55, 50))

    # Paste main paper onto canvas
    canvas.paste(paper, (paper_x, paper_y))
    draw = ImageDraw.Draw(canvas)

    # Large realistic metallic binder clip on right edge
    clip_rx, clip_ry = paper_x + paper_w - 25, paper_y + 440
    draw.rounded_rectangle([clip_rx, clip_ry, clip_rx + 55, clip_ry + 115], radius=6, fill=(195, 195, 200), outline=(130, 130, 135), width=2)
    draw.arc([clip_rx + 25, clip_ry - 30, clip_rx + 90, clip_ry + 55], 90, 270, fill=(110, 110, 115), width=4)
    draw.arc([clip_rx + 25, clip_ry + 60, clip_rx + 90, clip_ry + 145], 90, 270, fill=(110, 110, 115), width=4)

    # Bottom footer text
    footer_font = get_font(26, bold=True)
    foot_text = "REXION System Architecture 2026"
    f_bbox = draw.textbbox((0, 0), foot_text, font=footer_font)
    draw.text(((W - (f_bbox[2] - f_bbox[0])) // 2, H - 90), foot_text, font=footer_font, fill=(255, 255, 255))

    canvas.save(out_path, "JPEG", quality=95)
    return out_path


# ==============================================================================
# DESIGN 2: Mustard Yellow Folded Poster with Centered PC (Ref: 99414954...)
# ==============================================================================
def create_design_2_mustard_retro_poster(out_path: Path) -> Path:
    W, H = 1080, 1350
    # Rich warm mustard yellow (#F5BA04)
    canvas = Image.new("RGB", (W, H), (245, 186, 4))
    draw = ImageDraw.Draw(canvas)

    # 1. Subtle Paper Fold Creases (Horizontal + Vertical fold lines)
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
    pill_text = "intelligent job discovery"
    pb = draw.textbbox((0, 0), pill_text, font=pill_font)
    pw, ph = pb[2] - pb[0] + 36, pb[3] - pb[1] + 18
    px = (W - pw) // 2
    py = 180
    draw.rectangle([px, py, px + pw, py + ph], outline=(20, 20, 22), width=2)
    draw.text((px + 18, py + 8), pill_text, font=pill_font, fill=(20, 20, 22))

    # 3. High-contrast display serif headline with italics
    title_font = get_font(58, bold=True, serif=True)
    t1 = "Ever since I built REXION"
    t2 = "I knew Job Hunting shouldn't be"
    t3 = "a full-time manual job"

    draw.text(((W - draw.textbbox((0, 0), t1, font=title_font)[2]) // 2, 250), t1, font=title_font, fill=(20, 20, 22))
    draw.text(((W - draw.textbbox((0, 0), t2, font=title_font)[2]) // 2, 325), t2, font=title_font, fill=(20, 20, 22))
    draw.text(((W - draw.textbbox((0, 0), t3, font=title_font)[2]) // 2, 400), t3, font=title_font, fill=(20, 20, 22))

    # 4. Extract/Use the centered retro beige PC
    ref_pc_file = REF_DIR / "9941495476bd0631eea5bd2497dd461d.jpg"
    if ref_pc_file.exists():
        with Image.open(ref_pc_file) as ref_img:
            rw, rh = ref_img.size
            crop_box = (int(rw * 0.23), int(rh * 0.35), int(rw * 0.77), int(rh * 0.68))
            pc_crop = ref_img.crop(crop_box).convert("RGB")
            # Paint out old side annotation text from the crop with matching mustard yellow
            pc_draw = ImageDraw.Draw(pc_crop)
            mustard = (245, 186, 4)
            pc_draw.rectangle([0, 0, 95, 200], fill=mustard)
            pc_draw.rectangle([pc_crop.width - 100, 0, pc_crop.width, 240], fill=mustard)
            
            pc_w = 540
            pc_h = int(pc_w * (pc_crop.height / pc_crop.width))
            pc_resized = pc_crop.resize((pc_w, pc_h), Image.Resampling.LANCZOS)
            canvas.paste(pc_resized, ((W - pc_w) // 2, 530))

    # 5. Tiny witty side annotations placed cleanly outside the PC bounds
    side_font = get_font(18, bold=False)
    draw.text((70, 520), "manual applying takes hours\nautomated matching takes >>>", font=side_font, fill=(20, 20, 22))
    draw.text((W - 270, 570), "it's all about deterministic\nATS scoring //", font=side_font, fill=(20, 20, 22))

    # 6. Bottom Rhyme / Insight
    insight_font = get_font(21, serif=True)
    i1 = "Always indexing listings, filtering every single company"
    i2 = "Smart resume parser active at least twice a day"
    i3 = "Strictly low-latency architecture, zero unindexed scans"
    draw.text(((W - draw.textbbox((0, 0), i1, font=insight_font)[2]) // 2, 1020), i1, font=insight_font, fill=(20, 20, 22))
    draw.text(((W - draw.textbbox((0, 0), i2, font=insight_font)[2]) // 2, 1055), i2, font=insight_font, fill=(20, 20, 22))
    draw.text(((W - draw.textbbox((0, 0), i3, font=insight_font)[2]) // 2, 1090), i3, font=insight_font, fill=(20, 20, 22))

    # 7. Bottom Branding Signature
    brand_logo_font = get_font(34, bold=True)
    draw.text((280, 1200), "REXION", font=brand_logo_font, fill=(20, 20, 22))
    foot_font = get_font(18, bold=False)
    draw.text((450, 1205), "get in touch ->\nanshu.pal • github.com/rexmarchen", font=foot_font, fill=(20, 20, 22))

    canvas.save(out_path, "JPEG", quality=95)
    return out_path


# ==============================================================================
# DESIGN 3: Cobalt OS Blueprint Infographic Collage (Ref: 864b230f...)
# ==============================================================================
def create_design_3_cobalt_blueprint(out_path: Path) -> Path:
    W, H = 1080, 1350
    # Electric Cobalt Blue (#1832D7)
    canvas = Image.new("RGB", (W, H), (24, 50, 215))
    draw = ImageDraw.Draw(canvas)

    # Distressed white speckle / grunge texture
    import random
    random.seed(42)
    for _ in range(800):
        sx = random.randint(30, W - 30)
        sy = random.randint(30, H - 30)
        s_len = random.randint(1, 4)
        draw.line([(sx, sy), (sx + s_len, sy)], fill=(200, 220, 255), width=1)

    # 1. White border frame (2px solid white around entire poster)
    margin = 35
    draw.rectangle([margin, margin, W - margin, H - margin], outline=(255, 255, 255), width=2)

    # 2. Massive condensed typography across top
    title_font = get_font(110, bold=True)
    draw.text((55, 50), "REXION", font=title_font, fill=(255, 255, 255))
    draw.text((55, 170), "PIPELINE", font=title_font, fill=(255, 255, 255))

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

    # 3. Left technical explanation block
    body_font = get_font(18, bold=True)
    body_small = get_font(15, bold=False)

    lx = 65
    draw.text((lx, 350), "///////\nAN AI PIPELINE THAT ACTS AS A BRIDGE\nBETWEEN DISPERSED JOB BOARDS\nAND RELEVANT APPLICANTS.", font=body_font, fill=(255, 255, 255))

    draw.text((lx, 470), "WHAT IS REXION?", font=get_font(22, bold=True), fill=(255, 255, 255))
    draw.text((lx, 505), "REXION IS AN AUTOMATED SYSTEM PLATFORM\nTHAT CRAWLS, PARSES, AND SCORES\nJOB OPENINGS IN REAL-TIME, MATCHING\nCANDIDATES DETERMINISTICALLY.", font=body_small, fill=(255, 255, 255))

    draw.text((lx, 630), "CORE CAPABILITIES", font=get_font(22, bold=True), fill=(255, 255, 255))
    draw.text((lx, 665), "• MULTI-SOURCE INGESTION\n• REAL-TIME DEDUPLICATION\n• ATS KEYWORD SCORING\n• VECTOR RESUME RETRIEVAL\n• ONE-CLICK APPLICATION FLOW", font=body_small, fill=(255, 255, 255))

    # 4. Extract/Use the actual cutout floating CRT monitor & floppy disks without the old title text
    ref_os_file = REF_DIR / "864b230f28ed5658ac59d54c4ada307e.jpg"
    if ref_os_file.exists():
        with Image.open(ref_os_file) as ref_img:
            rw, rh = ref_img.size
            crop_box = (int(rw * 0.55), int(rh * 0.22), int(rw * 0.98), int(rh * 0.85))
            collage_crop = ref_img.crop(crop_box).convert("RGB")
            c_draw = ImageDraw.Draw(collage_crop)
            c_draw.rectangle([0, 0, 95, 110], fill=(24, 50, 215))

            cw_dest = 500
            ch_dest = int(cw_dest * (collage_crop.height / collage_crop.width))
            collage_resized = collage_crop.resize((cw_dest, ch_dest), Image.Resampling.LANCZOS)
            canvas.paste(collage_resized, (W - cw_dest - 30, 310))

    # 5. Bottom System Architecture Diagram Boxes
    arch_y = 990
    draw.text((lx, arch_y), "SYSTEM ARCHITECTURE PIPELINE", font=get_font(22, bold=True), fill=(255, 255, 255))

    box_w, box_h = 420, 42
    boxes = [
        "1. DISTRIBUTED DATA SCRAPERS",
        "2. SEMANTIC DEDUPLICATION (SHA-256)",
        "3. LLM RESUME PARSER & ATS FIT SCORE",
        "4. POSTGRESQL / VECTOR STORE INDEX"
    ]
    for i, b_text in enumerate(boxes):
        by = arch_y + 35 + (i * 48)
        draw.rectangle([lx, by, lx + box_w, by + box_h], outline=(255, 255, 255), width=1)
        draw.text((lx + 15, by + 12), b_text, font=get_font(15, bold=True), fill=(255, 255, 255))

    # Bottom Right Quote Box
    rx = 520
    draw.rectangle([rx, arch_y + 35, W - 55, arch_y + 225], outline=(255, 255, 255), width=1)
    q_text = "WITHOUT AUTOMATION, JOB SEARCH IS JUST A\nREPETITIVE CHORE. WITH REXION, IT BECOMES\nA PREDICTABLE, HIGH-THROUGHPUT SYSTEM."
    draw.text((rx + 20, arch_y + 55), q_text, font=get_font(15, bold=True), fill=(255, 255, 255))
    draw.line([(rx + 20, arch_y + 120), (W - 75, arch_y + 120)], fill=(255, 255, 255), width=1)
    draw.text((rx + 20, arch_y + 135), "CREATOR: ANSHU PAL\nFLAGSHIP: REXION.AI", font=get_font(15, bold=True), fill=(255, 255, 255))
    draw.text((rx + 270, arch_y + 135), "@REXMARCHEN\n2026 EDITION", font=get_font(15, bold=True), fill=(255, 255, 255))

    canvas.save(out_path, "JPEG", quality=95)
    return out_path


def main():
    print("Generating exact graphic design reference posters for REXION...")
    p1 = create_design_1_cutting_mat_stack(OUTPUT_DIR / "rexion_exact_ref1_cutting_mat.jpg")
    print(f"Created Design 1: {p1}")

    p2 = create_design_2_mustard_retro_poster(OUTPUT_DIR / "rexion_exact_ref2_mustard_poster.jpg")
    print(f"Created Design 2: {p2}")

    p3 = create_design_3_cobalt_blueprint(OUTPUT_DIR / "rexion_exact_ref3_cobalt_blueprint.jpg")
    print(f"Created Design 3: {p3}")


if __name__ == "__main__":
    main()
