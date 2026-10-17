"""
tests/test_overlay.py - Unit tests for Pillow typography engine.
"""

from pathlib import Path
from PIL import Image
from src.overlay import TypographyEngine, hex_to_rgb


def test_hex_to_rgb():
    assert hex_to_rgb("#1832D7") == (24, 50, 215)
    assert hex_to_rgb("#F5BA04") == (245, 186, 4)
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)


def test_apply_overlay():
    engine = TypographyEngine(Path("config/brand.yaml"))
    base_img = Image.new("RGB", (1024, 1280), color=(250, 248, 245))

    overlaid = engine.apply_overlay(
        base_img,
        headline="Architecting Autonomous AI Systems",
        layout_type="headline-on-photo",
        text_zone="top",
    )

    assert overlaid.size == (1024, 1280)
    assert overlaid.mode == "RGB"
