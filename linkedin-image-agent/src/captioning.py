"""
captioning.py - Generates precise style captions and metadata for training dataset using Vision LLM.
Produces paired .txt and .json files for Flux LoRA training.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image
from rich.console import Console
from rich.progress import track

from src.llm import get_llm, LLMClient

CAPTION_SYSTEM_PROMPT = """
You are an expert computer vision and diffusion LoRA fine-tuning specialist.
Your task is to analyze reference images from an aesthetic training set and create dense, descriptive visual captions.
Never use generic filler words like "This is an image of", "A photo showing", or "Masterpiece".
Focus purely on:
1. Core visual style (e.g. retro-futuristic technical diagram, flat matte graphic, industrial minimalism).
2. Props, subject & hardware (e.g. 1990s desktop monitor, CRT screen, mechanical keyboard, printed manual).
3. Materials and textures (e.g. folded newsprint, cutting mat grid, brushed aluminum, matte off-white card).
4. Color palette & lighting (e.g. cobalt blue and warm yellow accents on stark cream background, soft top-down diffused studio light).
5. Composition & negative space (e.g. 50% empty negative space in upper quadrant for typography overlay).
"""

CAPTION_USER_PROMPT = """
Analyze this training image and provide a JSON response with the following keys:
{
  "caption": "A concise 2-sentence visual description focusing on style, materials, colors, and layout without preamble.",
  "style_type": "The artistic genre/style (e.g., retro-tech poster, minimal editorial, technical blueprint)",
  "dominant_colors": ["color 1", "color 2", "color 3"],
  "materials": ["material 1", "material 2"],
  "props": ["prop or subject 1", "prop 2"],
  "lighting": "Description of lighting",
  "negative_space": "Where the clean, uncluttered space is located (e.g., top half, bottom right)"
}
Output valid JSON ONLY.
"""


def parse_llm_json(raw_text: str) -> Dict:
    """Extracts and parses JSON object from LLM response text."""
    clean = raw_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Fallback if wrapping or formatting was loose
        import re
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {
            "caption": clean.replace("\n", " "),
            "style_type": "editorial minimal",
            "dominant_colors": [],
            "materials": [],
            "props": [],
            "lighting": "diffused studio light",
            "negative_space": "center-top",
        }


def caption_image(
    image_path: Path,
    trigger_word: str = "rexstyle",
    llm: Optional[LLMClient] = None,
) -> Dict:
    """Generates caption and metadata dictionary for a single image."""
    llm = llm or get_llm()
    image_path = Path(image_path)

    raw_response = llm.analyze_image(
        image_input=image_path,
        prompt=CAPTION_USER_PROMPT,
        system_prompt=CAPTION_SYSTEM_PROMPT,
    )

    data = parse_llm_json(raw_response)
    raw_caption = data.get("caption", "").strip()

    # Prepend trigger word if not already present
    if not raw_caption.lower().startswith(trigger_word.lower()):
        full_caption = f"{trigger_word}, {raw_caption}"
    else:
        full_caption = raw_caption

    data["filename"] = image_path.name
    data["trigger_word"] = trigger_word
    data["full_caption"] = full_caption
    return data


def caption_dataset(
    clean_dir: Path,
    trigger_word: str = "rexstyle",
    overwrite: bool = False,
    delay_between_calls: float = 1.0,
) -> List[Dict]:
    """
    Iterates through all images in clean_dir, generating .txt and .json files.
    Skips images that already have .txt and .json files unless overwrite=True.
    """
    console = Console()
    clean_dir = Path(clean_dir)
    image_files = sorted([p for p in clean_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])

    if not image_files:
        console.print(f"[yellow]No images found in {clean_dir}[/yellow]")
        return []

    llm = get_llm()
    results = []

    console.print(f"[bold cyan]Captioning {len(image_files)} training images with trigger word '{trigger_word}'...[/bold cyan]")

    for idx, img_path in enumerate(image_files, 1):
        txt_path = img_path.with_suffix(".txt")
        json_path = img_path.with_suffix(".json")

        if not overwrite and txt_path.exists() and json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
                continue
            except Exception:
                pass

        console.print(f"[{idx}/{len(image_files)}] Captioning {img_path.name}...")
        try:
            metadata = caption_image(img_path, trigger_word=trigger_word, llm=llm)

            # Write .txt for LoRA training
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(metadata["full_caption"] + "\n")

            # Write .json for style guide & telemetry
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            results.append(metadata)
            time.sleep(delay_between_calls)

        except Exception as e:
            console.print(f"[red]Error captioning {img_path.name}: {e}[/red]")

    console.print(f"[bold green][OK] Captioning complete. {len(results)} images ready.[/bold green]")
    return results
