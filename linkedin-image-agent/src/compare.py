"""
compare.py - Side-by-side visual comparison engine (With LoRA vs Without LoRA).
Generates identical prompts with and without the trained LoRA adapter to evaluate aesthetic alignment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.table import Table

from src.generate import generate_candidates

console = Console()

DEFAULT_BENCHMARK_PROMPTS = [
    (
        "Vintage Terminal & Hardware",
        "rexstyle, tactile retro-futuristic still life of a vintage 1990s desktop CRT computer terminal with beige mechanical keyboard and exposed microchips on a warm cream drafting table, cobalt blue accent card, soft diffused overhead studio lighting, clean negative space in upper 45% of composition, high tactile clarity."
    ),
    (
        "Technical Document Collage",
        "rexstyle, an editorial design flat lay featuring layered textured newsprint schematics and architecture dossiers clipped with metal binder clips, resting on a green gridded cutting mat with terracotta accent marks, vast negative space at top for headline typography, deep focus, realistic soft drop shadows."
    ),
    (
        "Modernist Industrial Circuitry",
        "rexstyle, minimalist technical still life of ceramic microprocessors and vintage amber vacuum tubes arranged on a matte off-white background with subtle cobalt blue linework, generous empty negative space across top half, tactile paper texture, 35mm film grain."
    ),
]


def create_side_by_side(
    no_lora_path: Path,
    lora_path: Path,
    output_path: Path,
    prompt_title: str,
    lora_scale: float = 1.0,
) -> Path:
    """Stitches two 1024x1280 images side by side with clear comparison headers."""
    img_no_lora = Image.open(no_lora_path).convert("RGB")
    img_lora = Image.open(lora_path).convert("RGB")

    w, h = img_no_lora.size
    header_h = 100
    border = 20

    canvas_w = (w * 2) + (border * 3)
    canvas_h = h + header_h + (border * 2)

    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(15, 18, 24))  # #0F1218
    draw = ImageDraw.Draw(canvas)

    # Title Banner
    try:
        font_large = ImageFont.truetype("assets/fonts/heading.ttf", 36)
        font_sub = ImageFont.truetype("assets/fonts/body.ttf", 24)
    except Exception:
        font_large = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((border, 30), f"REXION Aesthetic Evaluation: {prompt_title}", font=font_large, fill=(255, 255, 255))

    # Paste Left: No LoRA
    left_x = border
    top_y = header_h
    canvas.paste(img_no_lora, (left_x, top_y))

    # Paste Right: With LoRA
    right_x = left_x + w + border
    canvas.paste(img_lora, (right_x, top_y))

    # Left Badge
    draw.rectangle([left_x + 20, top_y + 20, left_x + 360, top_y + 70], fill=(0, 0, 0, 200))
    draw.text((left_x + 35, top_y + 30), "BASE MODEL (No LoRA)", font=font_sub, fill=(240, 240, 240))

    # Right Badge
    draw.rectangle([right_x + 20, top_y + 20, right_x + 440, top_y + 70], fill=(24, 50, 215))
    draw.text((right_x + 35, top_y + 30), f"WITH LORA (scale={lora_scale})", font=font_sub, fill=(245, 186, 4))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=95)
    return output_path


def run_comparison(
    lora_url: Optional[str] = None,
    lora_scale: float = 1.0,
    output_dir: Path = Path("outputs/comparisons"),
    force_fallback: bool = False,
) -> List[Path]:
    """Generates side-by-side comparison images for the 3 benchmark prompts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check config/lora.json if lora_url was not passed
    if lora_url is None:
        lora_cfg = Path("config/lora.json")
        if lora_cfg.exists():
            try:
                with open(lora_cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    lora_url = data.get("lora_url")
            except Exception:
                pass

    comparison_paths = []
    console.print(f"[bold cyan]Running side-by-side LoRA comparison (scale={lora_scale})...[/bold cyan]")

    for idx, (title, prompt) in enumerate(DEFAULT_BENCHMARK_PROMPTS, 1):
        console.print(f"\n[bold]Evaluating Prompt {idx}/3:[/bold] {title}")

        # 1. Generate without LoRA
        console.print("  [dim]1. Generating BASE (without LoRA)...[/dim]")
        no_lora_results = generate_candidates(
            prompt=prompt.replace("rexstyle, ", ""),  # Base model without trigger
            lora_url=None,
            num_candidates=1,
            output_dir=output_dir / "raw_no_lora",
            force_fallback=force_fallback,
        )
        base_img = no_lora_results[0]

        # 2. Generate with LoRA
        console.print(f"  [dim]2. Generating WITH LORA (scale={lora_scale})...[/dim]")
        with_lora_results = generate_candidates(
            prompt=prompt,
            lora_url=lora_url,
            lora_scale=lora_scale,
            num_candidates=1,
            output_dir=output_dir / "raw_with_lora",
            force_fallback=force_fallback,
        )
        lora_img = with_lora_results[0]

        # 3. Stitch side-by-side
        stitched_path = output_dir / f"compare_prompt_{idx}.jpg"
        create_side_by_side(
            no_lora_path=base_img,
            lora_path=lora_img,
            output_path=stitched_path,
            prompt_title=title,
            lora_scale=lora_scale,
        )
        comparison_paths.append(stitched_path)
        console.print(f"  [green][OK] Comparison ready:[/green] {stitched_path}")

    # Display summary table
    table = Table(title="LoRA Side-by-Side Comparison Results")
    table.add_column("Prompt Title", style="cyan")
    table.add_column("Scale", style="magenta")
    table.add_column("Comparison Output File", style="green")

    for idx, (title, _) in enumerate(DEFAULT_BENCHMARK_PROMPTS):
        table.add_row(title, f"{lora_scale}", str(comparison_paths[idx]))

    console.print("\n")
    console.print(table)
    return comparison_paths
