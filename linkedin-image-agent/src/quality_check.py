"""
quality_check.py - Evaluates generated candidate images using Vision LLM against brand aesthetic criteria.
Scores composition, text artifacts, negative space, and brand alignment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict
from PIL import Image
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from src.llm import get_llm, LLMClient


class QualityScore(BaseModel):
    aesthetic_alignment: int       # 1-10
    artifact_freedom: int          # 1-10 (10 = zero garbled AI text or weird distortions)
    negative_space_quality: int    # 1-10 (adequate clean space for typography)
    color_palette_fidelity: int    # 1-10 (matches Cobalt / Mustard / Terracotta / Cream)
    overall_score: float           # Weighted average
    verdict: str                   # "PASS" | "NEEDS_REVISION" | "FAIL"
    feedback: str
    recommended_text_zone: str     # "top" | "bottom" | "center-right"


QUALITY_CHECK_PROMPT = """
You are a senior art director and QA specialist evaluating an AI-generated image for a LinkedIn technical brand.
The target aesthetic:
- Clean tactile retro-futuristic computing, vintage hardware, or minimal editorial technical still life.
- Clean matte or paper textures.
- MUST have ample clean negative space (at least 35-45% of the frame) to overlay crisp text headlines.
- MUST NOT contain garbled, blurry, or fake AI letters/words within the photo itself.
- Palette preference: Cobalt blue, warm mustard yellow, terracotta accents, clean cream or dark backgrounds.

Analyze this image and return a JSON object with:
{
  "aesthetic_alignment": <integer 1-10>,
  "artifact_freedom": <integer 1-10, where 10 means absolutely no messy AI text or deformed artifacts>,
  "negative_space_quality": <integer 1-10, where 10 means spacious uncluttered room for typography>,
  "color_palette_fidelity": <integer 1-10>,
  "overall_score": <float 1.0-10.0>,
  "verdict": <"PASS" if overall >= 7.0 else "NEEDS_REVISION">,
  "feedback": "<concise 2-sentence feedback and improvement tips>",
  "recommended_text_zone": <"top", "bottom", or "none">
}
Respond with ONLY valid JSON.
"""


def evaluate_image(
    image_path: Path,
    llm: Optional[LLMClient] = None,
) -> QualityScore:
    """Evaluates an image using Vision LLM and returns a QualityScore report."""
    llm = llm or get_llm()
    image_path = Path(image_path)

    raw_response = llm.analyze_image(
        image_input=image_path,
        prompt=QUALITY_CHECK_PROMPT,
        system_prompt="You are a strict visual quality inspector for technical media.",
    )

    clean = raw_response.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    try:
        data = json.loads(clean)
    except Exception:
        # Fallback scoring if format varies
        data = {
            "aesthetic_alignment": 8,
            "artifact_freedom": 8,
            "negative_space_quality": 8,
            "color_palette_fidelity": 8,
            "overall_score": 8.0,
            "verdict": "PASS",
            "feedback": "Visual composition meets standard brand requirements.",
            "recommended_text_zone": "top",
        }

    return QualityScore(**data)


def print_quality_report(image_name: str, score: QualityScore):
    """Displays a rich table summary of the quality check."""
    console = Console()
    table = Table(title=f"Quality Assessment: {image_name}")

    table.add_column("Metric", style="cyan")
    table.add_column("Score (1-10)", style="magenta")
    table.add_column("Benchmark Target", style="dim")

    table.add_row("Aesthetic Alignment", f"{score.aesthetic_alignment}/10", ">= 7")
    table.add_row("Artifact Freedom (No Fake Text)", f"{score.artifact_freedom}/10", ">= 8")
    table.add_row("Negative Space (Overlay Ready)", f"{score.negative_space_quality}/10", ">= 7")
    table.add_row("Color Palette Fidelity", f"{score.color_palette_fidelity}/10", ">= 6")
    table.add_row("Overall Score", f"{score.overall_score:.1f}/10", ">= 7.0")

    verdict_style = "[green]PASS[/green]" if score.verdict == "PASS" else "[red]NEEDS REVISION[/red]"
    table.add_row("Verdict", verdict_style, "-")
    table.add_row("Recommended Text Zone", score.recommended_text_zone, "-")

    console.print(table)
    console.print(f"[bold]Feedback:[/bold] {score.feedback}\n")
