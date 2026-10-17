"""
dataset_prep.py - Prepares, standardizes, deduplicates, and filters raw training images for LoRA.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageOps
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table


class ImageRecord(BaseModel):
    raw_name: str
    clean_name: Optional[str] = None
    original_size: Tuple[int, int]
    processed_size: Optional[Tuple[int, int]] = None
    status: str  # "Cleaned", "Skipped - Corrupt", "Skipped - Duplicate", "Skipped - Low Res"
    reason: Optional[str] = None
    dhash: Optional[str] = None


def compute_dhash(image: Image.Image, hash_size: int = 8) -> str:
    """Computes difference hash (dHash) for near-duplicate image detection."""
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    difference = []
    for row in range(hash_size):
        for col in range(hash_size):
            pixel_left = pixels[row * (hash_size + 1) + col]
            pixel_right = pixels[row * (hash_size + 1) + col + 1]
            difference.append(pixel_left > pixel_right)

    decimal_value = 0
    hex_parts = []
    for index, val in enumerate(difference):
        if val:
            decimal_value += 2 ** (index % 8)
        if (index % 8) == 7:
            hex_parts.append(hex(decimal_value)[2:].rjust(2, "0"))
            decimal_value = 0
    return "".join(hex_parts)


def hamming_distance(h1: str, h2: str) -> int:
    """Calculates bitwise Hamming distance between two hex hashes."""
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def standardize_image(
    image: Image.Image,
    min_long_side: int = 1024,
    max_long_side: int = 2048,
) -> Image.Image:
    """
    Normalizes color space to RGB (handles RGBA/P transparency by filling white),
    and scales dimensions so long edge is within [min_long_side, max_long_side].
    """
    # 1. Correct EXIF orientation
    image = ImageOps.exif_transpose(image)

    # 2. Convert to RGB with white background if alpha channel exists
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        alpha_image = image.convert("RGBA")
        background = Image.new("RGBA", alpha_image.size, (255, 255, 255, 255))
        alpha_composite = Image.alpha_composite(background, alpha_image)
        image = alpha_composite.convert("RGB")
    else:
        image = image.convert("RGB")

    w, h = image.size
    long_side = max(w, h)

    # 3. Scale long edge if too small or too large
    if long_side < min_long_side:
        scale = min_long_side / float(long_side)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    elif long_side > max_long_side:
        scale = max_long_side / float(long_side)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    return image


def process_dataset(
    raw_dir: Path,
    clean_dir: Path,
    min_dimension: int = 512,
    target_long_side: int = 1024,
    max_long_side: int = 2048,
    duplicate_threshold: int = 4,
) -> List[ImageRecord]:
    """
    Cleans, verifies, deduplicates, and standardizes images from raw_dir to clean_dir.
    """
    raw_dir = Path(raw_dir)
    clean_dir = Path(clean_dir)
    clean_dir.mkdir(parents=True, exist_ok=True)

    records: List[ImageRecord] = []
    known_hashes: Dict[str, str] = {}  # filename -> dhash

    # Supported image extensions
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    raw_files = [p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
    raw_files.sort(key=lambda p: p.name)

    for p in raw_files:
        try:
            with Image.open(p) as img:
                orig_size = img.size
                w, h = orig_size

                # Check minimum resolution
                if min(w, h) < min_dimension:
                    records.append(
                        ImageRecord(
                            raw_name=p.name,
                            original_size=orig_size,
                            status="Skipped - Low Res",
                            reason=f"Dimension {w}x{h} below minimum threshold {min_dimension}px",
                        )
                    )
                    continue

                # Compute perceptual dHash for deduplication
                img_hash = compute_dhash(img)

                # Check for near-duplicates
                is_duplicate = False
                dup_target = ""
                for existing_name, existing_hash in known_hashes.items():
                    dist = hamming_distance(img_hash, existing_hash)
                    if dist <= duplicate_threshold:
                        is_duplicate = True
                        dup_target = existing_name
                        break

                if is_duplicate:
                    records.append(
                        ImageRecord(
                            raw_name=p.name,
                            original_size=orig_size,
                            status="Skipped - Duplicate",
                            reason=f"Near-duplicate of {dup_target} (Hamming dist <= {duplicate_threshold})",
                            dhash=img_hash,
                        )
                    )
                    continue

                # Standardize & Resize
                cleaned_img = standardize_image(
                    img,
                    min_long_side=target_long_side,
                    max_long_side=max_long_side,
                )

                # Save clean JPG
                clean_name = f"{p.stem}.jpg"
                dest_path = clean_dir / clean_name
                cleaned_img.save(dest_path, "JPEG", quality=95, optimize=True)

                known_hashes[clean_name] = img_hash

                records.append(
                    ImageRecord(
                        raw_name=p.name,
                        clean_name=clean_name,
                        original_size=orig_size,
                        processed_size=cleaned_img.size,
                        status="Cleaned",
                        dhash=img_hash,
                    )
                )

        except Exception as e:
            records.append(
                ImageRecord(
                    raw_name=p.name,
                    original_size=(0, 0),
                    status="Skipped - Corrupt",
                    reason=str(e),
                )
            )

    return records


def print_prep_report(records: List[ImageRecord]):
    """Displays a formatted Rich table summary of dataset prep."""
    console = Console()
    table = Table(title="[bold blue]Dataset Preparation Summary[/bold blue]")

    table.add_column("Original File", style="cyan", no_wrap=True)
    table.add_column("Original Size", style="dim")
    table.add_column("Clean File", style="green")
    table.add_column("Clean Size", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="yellow")

    cleaned_count = 0
    for r in records:
        if r.status == "Cleaned":
            cleaned_count += 1
            status_style = "[green]CLEANED[/green]"
        elif "Duplicate" in r.status:
            status_style = "[yellow]DUPLICATE[/yellow]"
        elif "Low Res" in r.status:
            status_style = "[red]LOW RES[/red]"
        else:
            status_style = "[red]ERROR[/red]"

        orig_sz = f"{r.original_size[0]}x{r.original_size[1]}" if r.original_size != (0, 0) else "N/A"
        proc_sz = f"{r.processed_size[0]}x{r.processed_size[1]}" if r.processed_size else "-"

        table.add_row(
            r.raw_name,
            orig_sz,
            r.clean_name or "-",
            proc_sz,
            status_style,
            r.reason or "OK",
        )

    console.print(table)
    console.print(
        f"\n[bold green][OK] Successfully processed {cleaned_count}/{len(records)} images into clean dataset.[/bold green]\n"
    )
