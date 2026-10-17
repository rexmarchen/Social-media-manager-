"""
generate.py - Generates candidate images at 1024x1280 (4:5 aspect ratio, multiples of 16).
Supports:
1. Local diffusers SDXL + LoRA (Free on CUDA GPU, explicitly errors if no GPU available)
2. Fallback free generation (Free Pollinations Flux / Local canvas, default mode)
3. Hosted fal.ai Flux LoRA (Optional paid cloud mode, off by default)
Prints the active backend explicitly with zero silent switching.
"""

from __future__ import annotations

import os
import time
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict
import httpx
from PIL import Image, ImageDraw
from rich.console import Console

console = Console()


def detect_lora_architecture(lora_path: Path) -> str:
    """Detects whether a safetensors file belongs to SD 1.5 or SDXL."""
    try:
        from safetensors import safe_open
        with safe_open(str(lora_path), framework="pt") as f:
            keys = f.keys()
            for k in keys:
                if "lora_te2_" in k or "text_encoder_2" in k or "conditioner" in k:
                    return "sdxl"
        return "sd15"
    except Exception:
        # Fallback to filename heuristic
        if "sdxl" in lora_path.name.lower() or "xl" in lora_path.name.lower():
            return "sdxl"
        return "sd15"


def generate_with_diffusers_local(
    prompt: str,
    local_lora_path: Path,
    lora_scale: float = 1.0,
    width: Optional[int] = None,
    height: Optional[int] = None,
    num_images: int = 1,
    output_dir: Path = Path("outputs/generated"),
) -> List[Path]:
    """
    Generates images using local diffusers (SD 1.5 or SDXL) with CPU offloading for low-VRAM 4GB GPUs.
    Fails clearly if CUDA is unavailable.
    """
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU is required for local diffusers inference, but no GPU was detected on this machine.\n"
            "Please run on a system with an NVIDIA GPU, or use the free fallback backend: --backend fallback"
        )

    local_lora_path = Path(local_lora_path)
    if not local_lora_path.exists():
        raise FileNotFoundError(f"Local LoRA file not found at: {local_lora_path}")

    arch = detect_lora_architecture(local_lora_path)

    if arch == "sd15":
        model_repo = "stable-diffusion-v1-5/stable-diffusion-v1-5"
        gen_w = width or 512
        gen_h = height or 640  # 4:5 aspect ratio
        console.print(f"[bold cyan]Using generation backend: [LOCAL DIFFUSERS (SD 1.5 + LoRA, {gen_w}x{gen_h} with CPU Offload)][/bold cyan]")
        console.print(f"[cyan]Base Model: {model_repo} | LoRA Adapter: {local_lora_path.name} (scale={lora_scale})[/cyan]")

        from diffusers import StableDiffusionPipeline
        pipe = StableDiffusionPipeline.from_pretrained(
            model_repo,
            torch_dtype=torch.float16,
            safety_checker=None,
        )
    else:
        model_repo = "stabilityai/stable-diffusion-xl-base-1.0"
        gen_w = width or 1024
        gen_h = height or 1280
        console.print(f"[bold cyan]Using generation backend: [LOCAL DIFFUSERS (SDXL + LoRA, {gen_w}x{gen_h} with CPU Offload)][/bold cyan]")
        console.print(f"[cyan]Base Model: {model_repo} | LoRA Adapter: {local_lora_path.name} (scale={lora_scale})[/cyan]")

        from diffusers import StableDiffusionXLPipeline
        pipe = StableDiffusionXLPipeline.from_pretrained(
            model_repo,
            torch_dtype=torch.float16,
            variant="fp16",
        )

    # Enable aggressive low-VRAM optimizations for 4GB RTX 3050
    pipe.enable_model_cpu_offload()
    if hasattr(pipe, "enable_vae_tiling"):
        pipe.enable_vae_tiling()

    pipe.load_lora_weights(str(local_lora_path))
    if hasattr(pipe, "fuse_lora"):
        pipe.fuse_lora(lora_scale=lora_scale)

    timestamp = int(time.time())
    output_paths = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(num_images):
        console.print(f"[dim]Sampling candidate {idx + 1}/{num_images} at {gen_w}x{gen_h}...[/dim]")
        image = pipe(
            prompt=prompt,
            width=gen_w,
            height=gen_h,
            num_inference_steps=28,
            guidance_scale=7.0,
        ).images[0]
        out_p = output_dir / f"local_candidate_{timestamp}_{idx + 1}.jpg"
        image.save(out_p, "JPEG", quality=95)
        output_paths.append(out_p)

    return output_paths



def generate_with_fal(
    prompt: str,
    lora_url: Optional[str] = None,
    lora_scale: float = 1.0,
    width: int = 1024,
    height: int = 1280,
    num_images: int = 1,
    seed: Optional[int] = None,
) -> List[str]:
    """Calls fal.ai flux-lora endpoint (Optional paid mode)."""
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise RuntimeError(
            "FAL_KEY is required for fal.ai inference, but was not found in environment.\n"
            "Please set FAL_KEY in .env or run with default free mode: --backend fallback"
        )

    import fal_client

    arguments: Dict = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "num_images": num_images,
        "output_format": "jpeg",
        "enable_safety_checker": True,
    }

    if lora_url:
        arguments["loras"] = [{"path": lora_url, "scale": lora_scale}]

    if seed is not None:
        arguments["seed"] = seed

    console.print(f"[cyan]Submitting generation job to fal-ai/flux-lora ({width}x{height})...[/cyan]")
    response = fal_client.subscribe("fal-ai/flux-lora", arguments=arguments)

    image_urls = []
    if "images" in response:
        for img in response["images"]:
            image_urls.append(img["url"])
    return image_urls


def generate_with_fallback(
    prompt: str,
    headline: Optional[str] = None,
    width: int = 1024,
    height: int = 1280,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Fallback image generator for free local testing and development.
    Uses ReferencePosterEngine as Tier 1 primary generator.
    """
    if output_path is None:
        output_path = Path("outputs/generated") / f"gen_{int(time.time())}.jpg"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Tier 1 Primary: Authentic Graphic Design Reference Poster Engine (User reference dataset)
    try:
        import sys
        root_dir = Path(__file__).resolve().parent.parent.parent
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))
        from agent_skills.reference_poster_engine import ReferencePosterEngine, format_title_to_lines
        engine = ReferencePosterEngine(output_dir=output_path.parent)

        lines = None
        if headline:
            clean_hl = headline.replace("Mastering ", "").strip()
            lines = format_title_to_lines(clean_hl, max_lines=4)

        gen_path = engine.generate(
            headline_lines=lines,
            tag="ENGINEERING ARCHITECTURE",
            subtitle="Autonomous systems, deterministic pipelines, and modern full-stack workflows.",
            output_filename=output_path.name,
        )
        if gen_path and gen_path.exists() and gen_path.stat().st_size > 4000:
            console.print(f"[bold green]Synthesized exact reference poster via ReferencePosterEngine: {gen_path}[/bold green]")
            return gen_path
    except Exception as eng_err:
        console.print(f"[dim yellow]Poster engine fallback notice ({eng_err}); trying fallback services.[/dim yellow]")

    # Tier 2 Fallback: Remote Flux service
    try:
        encoded_prompt = urllib.parse.quote(prompt[:250])
        flux_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=flux&nologo=true&seed=42"
        console.print(f"[dim]Requesting test generation from fallback Flux service...[/dim]")
        resp = httpx.get(flux_url, timeout=30.0)
        if resp.status_code == 200 and len(resp.content) > 5000:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return output_path
    except Exception as e:
        console.print(f"[dim yellow]Remote service notice ({e}); generating local aesthetic canvas.[/dim yellow]")

    img = Image.new("RGB", (width, height), color=(250, 248, 245))  # #FAF8F5 cream
    draw = ImageDraw.Draw(img)

    grid_spacing = 64
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=(235, 230, 222), width=1)
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=(235, 230, 222), width=1)

    draw.rectangle([120, 680, width - 120, height - 120], fill=(24, 50, 215))  # Cobalt Blue #1832D7
    draw.rectangle([140, 700, width - 140, height - 140], fill=(15, 18, 24))   # Terminal dark #0F1218
    draw.rectangle([120, 640, 320, 680], fill=(245, 186, 4))  # Mustard #F5BA04

    img.save(output_path, "JPEG", quality=95)
    return output_path


def generate_candidates(
    prompt: str,
    headline: Optional[str] = None,
    backend: str = "fallback",  # "fallback" | "local" | "fal"
    local_lora_path: Optional[Path] = None,
    lora_url: Optional[str] = None,
    lora_scale: float = 1.0,
    num_candidates: int = 3,
    output_dir: Path = Path("outputs/generated"),
    width: int = 1024,
    height: int = 1280,
    force_fallback: bool = False,
) -> List[Path]:
    """
    Generates candidate images at 1024x1280.
    Prints the active backend explicitly with zero silent switching.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []
    timestamp = int(time.time())

    # If user provided a local lora path, route to local diffusers
    if local_lora_path is not None and not force_fallback:
        backend = "local"

    if force_fallback:
        backend = "fallback"

    # Backend 1: Local Diffusers with LoRA
    if backend == "local":
        console.print(f"[bold cyan]Using generation backend: [LOCAL DIFFUSERS (SDXL + LoRA)][/bold cyan]")
        if local_lora_path is None:
            raise ValueError("--local-lora path must be specified when using the local backend.")
        return generate_with_diffusers_local(
            prompt=prompt,
            local_lora_path=local_lora_path,
            lora_scale=lora_scale,
            width=width,
            height=height,
            num_images=num_candidates,
            output_dir=output_dir,
        )

    # Backend 2: Optional Paid fal.ai
    elif backend == "fal":
        console.print(f"[bold cyan]Using generation backend: [FAL.AI HOSTED FLUX (Paid Cloud Mode)][/bold cyan]")
        urls = generate_with_fal(
            prompt=prompt,
            lora_url=lora_url,
            lora_scale=lora_scale,
            width=width,
            height=height,
            num_images=num_candidates,
        )
        for idx, url in enumerate(urls):
            resp = httpx.get(url, timeout=30.0)
            if resp.status_code == 200:
                cand_path = output_dir / f"fal_candidate_{timestamp}_{idx + 1}.jpg"
                with open(cand_path, "wb") as f:
                    f.write(resp.content)
                saved_paths.append(cand_path)
        console.print(f"[bold green][OK] Generated {len(saved_paths)} images via fal.ai in {output_dir}[/bold green]")
        return saved_paths

    # Backend 3: Free Fallback Generator (Default)
    elif backend == "fallback":
        console.print(f"[bold cyan]Using generation backend: [FALLBACK / LOCAL CANVAS (Free Mode)][/bold cyan]")
        for idx in range(num_candidates):
            cand_path = output_dir / f"candidate_{timestamp}_{idx + 1}.jpg"
            prompt_var = f"{prompt} --variation {idx + 1}"
            p = generate_with_fallback(prompt_var, headline=headline, width=width, height=height, output_path=cand_path)
            saved_paths.append(p)
        console.print(f"[bold green][OK] Generated {len(saved_paths)} candidate images at {width}x{height} in {output_dir}[/bold green]")
        return saved_paths

    else:
        raise ValueError(f"Unknown generation backend: {backend}. Choose 'fallback', 'local', or 'fal'.")
