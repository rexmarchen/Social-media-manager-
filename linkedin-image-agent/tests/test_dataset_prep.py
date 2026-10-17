"""
tests/test_dataset_prep.py - Unit tests for image standardization and deduplication.
"""

from PIL import Image
from src.dataset_prep import compute_dhash, hamming_distance, standardize_image


def test_dhash_identical_images():
    img1 = Image.new("RGB", (200, 200), color=(128, 128, 128))
    img2 = Image.new("RGB", (200, 200), color=(128, 128, 128))

    h1 = compute_dhash(img1)
    h2 = compute_dhash(img2)
    assert hamming_distance(h1, h2) == 0


def test_standardize_image_dimensions():
    # Small image (500x600) scaled to long side 1024
    img = Image.new("RGB", (500, 600), color=(255, 255, 255))
    cleaned = standardize_image(img, min_long_side=1024, max_long_side=2048)

    w, h = cleaned.size
    assert max(w, h) == 1024
    assert cleaned.mode == "RGB"


def test_standardize_rgba_converts_to_rgb():
    # Image with transparency
    img = Image.new("RGBA", (1024, 1024), color=(255, 0, 0, 128))
    cleaned = standardize_image(img, min_long_side=1024, max_long_side=2048)
    assert cleaned.mode == "RGB"
