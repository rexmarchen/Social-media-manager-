"""
tests/test_export.py - Unit tests for export and carousel creation.
"""

import tempfile
from pathlib import Path
from PIL import Image
from src.export import (
    resize_to_portrait,
    resize_to_square,
    resize_to_landscape,
    save_optimized_jpeg,
    create_carousel_pdf,
)


def test_resize_dimensions():
    # Input is 1024x1280 (4:5)
    img = Image.new("RGB", (1024, 1280), color=(100, 100, 100))

    portrait = resize_to_portrait(img)
    assert portrait.size == (1080, 1350)

    square = resize_to_square(img)
    assert square.size == (1080, 1080)

    landscape = resize_to_landscape(img)
    assert landscape.size == (1200, 627)


def test_save_optimized_jpeg():
    with tempfile.TemporaryDirectory() as tmpdir:
        img = Image.new("RGB", (1080, 1350), color=(200, 200, 200))
        out_file = Path(tmpdir) / "test_post.jpg"
        saved = save_optimized_jpeg(img, out_file)
        assert saved.exists()
        assert saved.stat().st_size < 5 * 1024 * 1024


def test_carousel_pdf():
    with tempfile.TemporaryDirectory() as tmpdir:
        slides = [
            Image.new("RGB", (1024, 1280), color=(255, 0, 0)),
            Image.new("RGB", (1024, 1280), color=(0, 255, 0)),
            Image.new("RGB", (1024, 1280), color=(0, 0, 255)),
        ]
        out_pdf = Path(tmpdir) / "carousel.pdf"
        pdf_path = create_carousel_pdf(slides, out_pdf)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
