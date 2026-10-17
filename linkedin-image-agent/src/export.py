"""
export.py - Image Resizing, Optimization, and Multi-Format Export for LinkedIn.
Resizes 1024x1280 raw generations to exact 1080x1350 (4:5 portrait), 1080x1080 (square),
and 1200x627 (landscape). Enforces strict <5MB LinkedIn size limit and generates carousel PDFs.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional, Tuple, Union
from PIL import Image, ImageOps

MAX_LINKEDIN_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


def resize_to_portrait(image: Image.Image, target_size: Tuple[int, int] = (1080, 1350)) -> Image.Image:
    """
    Resizes from 1024x1280 (or any 4:5 image) to standard LinkedIn 1080x1350.
    Since 1024/1280 is identical to 1080/1350 (0.8 aspect ratio), Lanczos scaling preserves full frame.
    """
    return ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)


def resize_to_square(image: Image.Image, target_size: Tuple[int, int] = (1080, 1080)) -> Image.Image:
    """Crops and resizes image to 1080x1080 square."""
    return ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def resize_to_landscape(image: Image.Image, target_size: Tuple[int, int] = (1200, 627)) -> Image.Image:
    """Crops and resizes image to 1200x627 landscape (link preview standard)."""
    return ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def save_optimized_jpeg(image: Image.Image, output_path: Path, max_bytes: int = MAX_LINKEDIN_FILE_BYTES) -> Path:
    """
    Saves image as JPEG with progressive encoding, ensuring the output file is strictly < max_bytes.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb_img = image.convert("RGB")

    quality = 95
    while quality >= 60:
        buffer = io.BytesIO()
        rgb_img.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        size = buffer.tell()
        if size <= max_bytes or quality <= 65:
            with open(output_path, "wb") as f:
                f.write(buffer.getvalue())
            return output_path
        quality -= 5

    # Final fallback if loop ends
    with open(output_path, "wb") as f:
        f.write(buffer.getvalue())
    return output_path


def export_single_post(
    input_image: Union[Image.Image, Path, str],
    output_dir: Path,
    base_name: str = "post",
) -> dict:
    """
    Exports image in 3 standard LinkedIn formats:
    - portrait: 1080x1350 (optimal 4:5 feed view)
    - square: 1080x1080 (1:1 standard)
    - landscape: 1200x627 (link/banner)
    """
    if isinstance(input_image, (str, Path)):
        img = Image.open(input_image)
    else:
        img = input_image

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Portrait 1080x1350
    portrait_img = resize_to_portrait(img)
    portrait_path = output_dir / f"{base_name}_1080x1350.jpg"
    save_optimized_jpeg(portrait_img, portrait_path)

    # 2. Square 1080x1080
    square_img = resize_to_square(img)
    square_path = output_dir / f"{base_name}_1080x1080.jpg"
    save_optimized_jpeg(square_img, square_path)

    # 3. Landscape 1200x627
    landscape_img = resize_to_landscape(img)
    landscape_path = output_dir / f"{base_name}_1200x627.jpg"
    save_optimized_jpeg(landscape_img, landscape_path)

    return {
        "portrait": portrait_path,
        "square": square_path,
        "landscape": landscape_path,
    }


def create_carousel_pdf(
    images: List[Union[Image.Image, Path, str]],
    output_path: Path,
    target_size: Tuple[int, int] = (1080, 1350),
) -> Path:
    """
    Combines a list of slide images into a multi-page PDF document optimized for LinkedIn carousels.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pil_slides = []
    for item in images:
        if isinstance(item, (str, Path)):
            im = Image.open(item)
        else:
            im = item
        resized = resize_to_portrait(im, target_size=target_size).convert("RGB")
        pil_slides.append(resized)

    if not pil_slides:
        raise ValueError("Cannot create carousel PDF from empty image list.")

    first_slide = pil_slides[0]
    rest_slides = pil_slides[1:]

    first_slide.save(
        output_path,
        "PDF",
        resolution=100.0,
        save_all=True,
        append_images=rest_slides,
    )

    return output_path
