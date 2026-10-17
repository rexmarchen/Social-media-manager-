"""
Visual Quality Assurance (QA) Skill
-----------------------------------
Evaluates synthesized and composited images for sharpness, resolution, aspect ratio,
contrast, readability, and brand compliance, providing explicit scores and failure diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List
from PIL import Image, ImageStat, ImageFilter
from .brand_consistency import BrandManager

log = logging.getLogger("visual_qa")


@dataclass
class QAResult:
    passed: bool
    score: float
    resolution: tuple[int, int]
    sharpness_score: float
    contrast_score: float
    brightness_score: float
    failure_reasons: List[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisualQA:
    def __init__(self, brand_manager: BrandManager | None = None):
        self.brand = brand_manager or BrandManager()
        self.thresholds = self.brand.get_qa_thresholds()

    def evaluate(self, image_path: Path | str, topic: str = "") -> QAResult:
        path = Path(image_path)
        if not path.exists():
            return QAResult(
                passed=False,
                score=0.0,
                resolution=(0, 0),
                sharpness_score=0.0,
                contrast_score=0.0,
                brightness_score=0.0,
                failure_reasons=["Image file does not exist"],
            )

        with Image.open(path) as img:
            rgb = img.convert("RGB")
            w, h = rgb.size

            # 1. Resolution Check (supports 1200x627 horizontal, 1080x1080 square, 1080x1350 portrait)
            res_pass = (w >= 1000 and h >= 600) or (w >= 1000 and h >= 1000) or ((w * h) >= 700000)

            # 2. Contrast & Brightness Check
            stat = ImageStat.Stat(rgb)
            mean_brightness = sum(stat.mean) / 3.0
            contrast = sum(stat.stddev) / 3.0

            contrast_pass = contrast >= self.thresholds.get("min_contrast", 20.0)
            brightness_pass = 8.0 <= mean_brightness <= 245.0  # allows sleek dark-mode while catching pure black void (< 8)

            # 3. Sharpness Check via edge detection variance
            gray = rgb.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            sharpness = edge_stat.var[0]
            sharpness_pass = sharpness >= self.thresholds.get("min_sharpness", 10.0)

            # 4. Aspect Ratio Check (LinkedIn standard ~ 1.91:1)
            aspect = w / h
            aspect_pass = 1.6 <= aspect <= 2.1 or (0.95 <= aspect <= 1.05)

            # Scoring calculation (0 - 100)
            score = 100.0
            failures = []

            if not res_pass:
                score -= 30.0
                failures.append(f"Resolution {w}x{h} is below minimum requirement (1000x600)")
            if not contrast_pass:
                score -= 25.0
                failures.append(f"Low image contrast ({contrast:.1f} < {self.thresholds.get('min_contrast', 20.0)})")
            if not brightness_pass:
                score -= 25.0
                failures.append(f"Extreme lighting imbalance (brightness: {mean_brightness:.1f})")
            if not sharpness_pass:
                score -= 20.0
                failures.append(f"Image lacks clarity or edge sharpness ({sharpness:.1f} < {self.thresholds.get('min_sharpness', 10.0)})")
            if not aspect_pass:
                score -= 15.0
                failures.append(f"Non-standard aspect ratio ({aspect:.2f}:1)")

            pass_score = self.thresholds.get("pass_score", 70.0)
            critical_failures = [f for f in failures if "Resolution" in f or "Extreme lighting" in f]
            passed = (score >= pass_score) and len(critical_failures) == 0

            diagnostics = {
                "width": w,
                "height": h,
                "aspect_ratio": f"{aspect:.2f}:1",
                "mean_brightness": round(mean_brightness, 2),
                "contrast_stddev": round(contrast, 2),
                "sharpness_var": round(sharpness, 2),
                "threshold_pass_score": pass_score,
                "topic": topic,
            }

            log.info("Visual QA Result: Score=%.1f/100, Passed=%s, Failures=%s", score, passed, failures)
            return QAResult(
                passed=passed,
                score=max(0.0, score),
                resolution=(w, h),
                sharpness_score=round(sharpness, 2),
                contrast_score=round(contrast, 2),
                brightness_score=round(mean_brightness, 2),
                failure_reasons=failures,
                diagnostics=diagnostics,
            )
