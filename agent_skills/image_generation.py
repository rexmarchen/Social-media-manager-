"""
AI Image Generation Skill
-------------------------
Multi-provider image synthesis engine supporting Gemini/Imagen, Flux/Pollinations,
and local deterministic rendering with strict timeouts, aspect ratio enforcement, and cost controls.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import requests
from PIL import Image, ImageDraw

log = logging.getLogger("image_generation")

ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT_DIR / "generated_images"
GENERATED_DIR.mkdir(exist_ok=True)


class ImageGenerator:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or GENERATED_DIR
        self.output_dir.mkdir(exist_ok=True)

    def generate(
        self,
        prompt: str,
        width: int = 1200,
        height: int = 627,
        provider_preference: str | None = None,
    ) -> Path:
        """
        Synthesizes an image using resilient multi-tier fallback.
        Returns the absolute path to the generated image file.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target_path = self.output_dir / f"gen-{timestamp}.jpg"

        # Tier 0: Authentic Graphic Design Reference Poster Engine (User reference dataset)
        try:
            from agent_skills.reference_poster_engine import ReferencePosterEngine
            log.info("Requesting synthesis via ReferencePosterEngine (authentic graphic design poster)...")
            engine = ReferencePosterEngine(output_dir=self.output_dir)
            poster_path = engine.generate(
                headline_lines=None,
                tag="ENGINEERING ARCHITECTURE",
                subtitle=prompt[:140],
                output_filename=f"gen-{timestamp}.jpg",
            )
            if poster_path and poster_path.exists() and poster_path.stat().st_size > 4096:
                log.info("Poster generated successfully via ReferencePosterEngine (%d bytes)", poster_path.stat().st_size)
                return poster_path
        except Exception as exc:
            log.warning("ReferencePosterEngine fallback: %s", exc)

        # Tier 1: Graphic Design Synthesis (Editorial brand palette fallback)
        try:
            log.info("Requesting synthesis via Flux/Pollinations provider (1080x1350)...")
            encoded = quote(f"rexstyle, {prompt}, graphic design poster, tactile editorial minimalism, cutting mat, typography, retro computing, muted clean colors, authentic physical print")
            seed = int(time.time() * 1000) % 1000000
            url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={seed}"
            resp = requests.get(url, timeout=35)
            if resp.status_code == 200 and len(resp.content) > 4096:
                target_path.write_bytes(resp.content)
                with Image.open(target_path) as im:
                    if im.size != (width, height):
                        im_resized = im.resize((width, height), Image.Resampling.LANCZOS)
                        im_resized.save(target_path, "JPEG", quality=95)
                log.info("Image generated successfully via Flux (%d bytes)", target_path.stat().st_size)
                return target_path
        except Exception as exc:
            log.warning("Flux synthesis skipped: %s", exc)

        # Tier 2: Google Gemini / Imagen (if available in environment)
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                log.info("Attempting synthesis via Google Imagen API...")
                model = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
                is_imagen = model.startswith("imagen")
                endpoint = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"
                    if is_imagen
                    else f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                )
                headers = {"Content-Type": "application/json", "x-goog-api-key": gemini_key}
                body = (
                    {
                        "instances": [{"prompt": prompt}],
                        "parameters": {"sampleCount": 1, "aspectRatio": "16:9", "outputOptions": {"mimeType": "image/jpeg"}},
                    }
                    if is_imagen
                    else {"contents": [{"parts": [{"text": prompt}]}]}
                )
                r = requests.post(endpoint, headers=headers, json=body, timeout=40)
                if r.status_code == 200:
                    data = r.json()
                    b64_data = data.get("predictions", [{}])[0].get("bytesBase64Encoded")
                    if not b64_data:
                        for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                            if part.get("inlineData", {}).get("data"):
                                b64_data = part["inlineData"]["data"]
                                break
                    if b64_data:
                        target_path.write_bytes(base64.b64decode(b64_data))
                        log.info("Image generated successfully via Google Imagen.")
                        return target_path
            except Exception as e:
                log.warning("Google Imagen fallback failed: %s", e)

        # Tier 3: Local Deterministic Tech Graphic Generator (100% offline & foolproof)
        log.info("Generating local deterministic high-contrast tech gradient canvas...")
        img = Image.new("RGB", (width, height), color=(11, 15, 23))
        draw = ImageDraw.Draw(img)

        # Draw deep ambient glow nodes
        draw.ellipse([(width - 400, -100), (width + 200, 500)], fill=(20, 28, 48))
        draw.ellipse([(-100, height - 300), (300, height + 100)], fill=(15, 30, 45))

        # Geometric matrix grid lines
        for x in range(0, width, 60):
            draw.line([(x, 0), (x, height)], fill=(25, 35, 55), width=1)
        for y in range(0, height, 60):
            draw.line([(0, y), (width, y)], fill=(25, 35, 55), width=1)

        # Glowing accent core node
        cx, cy = int(width * 0.72), int(height * 0.5)
        for r in range(120, 10, -15):
            alpha_color = (0, min(229, r * 2), 255)
            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=alpha_color, width=2)

        img.save(target_path, "JPEG", quality=95)
        log.info("Local deterministic image generated: %s", target_path)
        return target_path
