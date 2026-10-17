"""
style_guide.py - Synthesizes dataset metadata into a comprehensive visual Style Guide.
Saves to config/style_guide.md for use by the prompt engineering and quality check modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console

from src.llm import get_llm, LLMClient

STYLE_GUIDE_SYNTHESIS_PROMPT = """
You are an elite creative director and visual brand strategist specializing in developer & AI tech aesthetics.
Below is an aggregated JSON dump of annotations from a curated style dataset (16 reference images) for the brand "REXION" / "Anshu Pal" using trigger word "rexstyle".

Analyze all recurring patterns, materials, colors, subjects, lighting, and composition rules.
Then, write a complete, highly-structured, production-ready Markdown Style Guide.

Include these exact sections:
# REXION Visual Style Guide (Trigger: `rexstyle`)

## 1. Core Aesthetic Philosophy
(Define the distinct intersection of retro-computing, tactile engineering, editorial minimalism, and technical architecture)

## 2. Dominant Color Palette & Color Usage Rules
(Table of primary, secondary, background, and accent colors with HEX codes and usage percentages)

## 3. Signature Physical Props, Subjects & Textures
(Bullet list of iconic objects: vintage computers, CRT screens, folded paper, tactile cutting mats, microchips, ceramic surfaces)

## 4. Composition, Layout & Negative Space Rules
(Rules for 4:5 aspect ratio, where negative space must be preserved for text overlays, margins)

## 5. Lighting, Camera Angles & Depth of Field
(Top-down flat lays, 45-degree isometric studio perspectives, soft diffused shadows, high tactile clarity)

## 6. Prohibited Visual Tropes (The "Never Use" List)
(Explicit list of clichés to avoid: cheesy 3D avatars, generic stock photos, neon rainbows, garbled AI text)

## 7. Master Flux Prompt Formula & Golden Template
(Exact syntax for prompting Flux LoRA with `rexstyle`)

Return ONLY the markdown content.
"""


def aggregate_dataset_metadata(clean_dir: Path) -> List[Dict]:
    """Reads all .json metadata files from the clean dataset directory."""
    clean_dir = Path(clean_dir)
    json_files = sorted(clean_dir.glob("*.json"))
    metadata = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                metadata.append(json.load(f))
        except Exception:
            pass
    return metadata


def generate_style_guide(
    clean_dir: Path,
    output_path: Path,
    brand_config_path: Optional[Path] = None,
    llm: Optional[LLMClient] = None,
) -> str:
    """Aggregates image metadata and uses LLM to generate config/style_guide.md."""
    console = Console()
    llm = llm or get_llm()
    clean_dir = Path(clean_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = aggregate_dataset_metadata(clean_dir)
    if not metadata:
        console.print(f"[yellow]Warning: No metadata .json files found in {clean_dir}.[/yellow]")
        # Provide base seed metadata if not yet captioned
        metadata = [
            {
                "style_type": "editorial retro-tech minimalism",
                "dominant_colors": ["#1832D7", "#F5BA04", "#E85A18", "#FAF8F5"],
                "materials": ["folded newsprint", "matte ceramic", "cutting mat grid"],
                "props": ["vintage CRT computer monitor", "retro mechanical keyboard", "technical spec sheet"],
                "lighting": "diffused top-down studio lighting",
                "negative_space": "top 45% clear for headline typography",
            }
        ]

    # Summarize items
    summary_data = {
        "sample_count": len(metadata),
        "styles_observed": list({m.get("style_type", "") for m in metadata if m.get("style_type")}),
        "dominant_colors": [c for m in metadata for c in m.get("dominant_colors", [])][:20],
        "materials": list({mat for m in metadata for mat in m.get("materials", [])}),
        "props": list({prop for m in metadata for prop in m.get("props", [])}),
        "lighting_modes": list({m.get("lighting", "") for m in metadata if m.get("lighting")}),
        "negative_space_notes": list({m.get("negative_space", "") for m in metadata if m.get("negative_space")}),
    }

    prompt = (
        f"{STYLE_GUIDE_SYNTHESIS_PROMPT}\n\n"
        f"Aggregated Dataset Metadata:\n{json.dumps(summary_data, indent=2)}"
    )

    console.print("[cyan]Synthesizing visual Style Guide from dataset metadata...[/cyan]")
    guide_markdown = llm.generate_text(prompt, temperature=0.4)

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(guide_markdown + "\n")

    console.print(f"[bold green][OK] Style Guide saved to {output_path}[/bold green]")
    return guide_markdown
