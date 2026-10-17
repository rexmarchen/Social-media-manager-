"""
tests/test_quality_check.py - Tests quality check scoring against deliberately bad images.
"""

import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
import random
import pytest

from src.quality_check import evaluate_image, QualityScore


def create_deliberately_bad_image(output_path: Path) -> Path:
    """
    Creates an image that violates brand aesthetic:
    - High-frequency chaotic noise
    - Garbled random pseudo-characters across the entire surface
    - Zero negative space
    - Ugly discordant colors (neon green and violent magenta)
    """
    img = Image.new("RGB", (600, 800), color=(255, 0, 255))
    draw = ImageDraw.Draw(img)

    # Random noisy lines covering every quadrant
    random.seed(42)
    for _ in range(300):
        x1 = random.randint(0, 600)
        y1 = random.randint(0, 800)
        x2 = random.randint(0, 600)
        y2 = random.randint(0, 800)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=random.randint(2, 6))

    # Scribble pseudo-text across top, center, and bottom
    for y in range(50, 750, 60):
        draw.text((30, y), "X%#@98!*GARBLE_AI_TEXT_GLITCH_ZZZ_OVERFLOW", fill=(0, 255, 0))

    img.save(output_path, "JPEG", quality=80)
    return output_path


def test_quality_check_flags_bad_image():
    """Confirms that a cluttered, garbled image receives a failing or low score from Vision QA."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_img_path = Path(tmpdir) / "bad_image.jpg"
        create_deliberately_bad_image(bad_img_path)

        score = evaluate_image(bad_img_path)
        assert isinstance(score, QualityScore)

        # Confirm that either overall score is failing or negative space/artifact metrics are penalized
        is_penalized = (
            score.overall_score < 7.0
            or score.verdict == "NEEDS_REVISION"
            or score.negative_space_quality <= 5
            or score.artifact_freedom <= 6
        )
        assert is_penalized, f"Expected QA to penalize bad image, but received: {score}"
