"""
cli.py - Command-Line Interface for linkedin-image-agent (Phase 1).
Provides commands: prep, caption, styleguide, generate, check, overlay, export, and create-basic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import typer
from PIL import Image
from rich.console import Console

from src.dataset_prep import process_dataset, print_prep_report
from src.captioning import caption_dataset
from src.style_guide import generate_style_guide
from src.prompt_writer import PromptWriter
from src.generate import generate_candidates
from src.quality_check import evaluate_image, print_quality_report
from src.overlay import TypographyEngine
from src.export import export_single_post, create_carousel_pdf

app = typer.Typer(
    help="linkedin-image-agent: Autonomous visual production pipeline for LinkedIn.",
    add_completion=False,
)
console = Console()

BRAND_CONFIG = Path("config/brand.yaml")
STYLE_GUIDE_PATH = Path("config/style_guide.md")


@app.command()
def prep(
    raw_dir: Path = typer.Option(Path("dataset/raw"), help="Path to raw input images"),
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to cleaned dataset"),
    target_long: int = typer.Option(1024, help="Target long-side resolution (e.g. 1024)"),
    max_long: int = typer.Option(2048, help="Maximum long-side resolution"),
):
    """Cleans, resizes, deduplicates (dHash), and standardizes training images."""
    console.print(f"[bold cyan]Starting dataset preparation from {raw_dir} -> {clean_dir}...[/bold cyan]")
    records = process_dataset(
        raw_dir=raw_dir,
        clean_dir=clean_dir,
        target_long_side=target_long,
        max_long_side=max_long,
    )
    print_prep_report(records)


@app.command()
def caption(
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to clean training images"),
    trigger_word: str = typer.Option("rexstyle", help="LoRA trigger word"),
    overwrite: bool = typer.Option(False, help="Re-generate existing captions"),
):
    """Uses Vision LLM to generate descriptive .txt captions and .json metadata."""
    caption_dataset(clean_dir=clean_dir, trigger_word=trigger_word, overwrite=overwrite)


@app.command()
def styleguide(
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to clean training images"),
    output: Path = typer.Option(STYLE_GUIDE_PATH, help="Path for generated Markdown style guide"),
):
    """Synthesizes dataset visual patterns into config/style_guide.md."""
    generate_style_guide(clean_dir=clean_dir, output_path=output)


@app.command("export-training-kit")
def export_training_kit(
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to clean training images"),
    output_zip: Path = typer.Option(Path("outputs/training_kit.zip"), help="Path for dataset zip"),
    trigger_word: str = typer.Option("rexstyle", help="LoRA trigger word"),
    steps: int = typer.Option(1200, help="Training steps for Colab/Kaggle"),
    rank: int = typer.Option(16, help="LoRA network rank (dim)"),
    save_every: int = typer.Option(250, help="Checkpoint frequency in steps"),
):
    """Packages dataset/clean into outputs/training_kit.zip, writes Colab notebook and TRAINING_GUIDE.md."""
    from src.training_kit import export_training_kit_bundle
    export_training_kit_bundle(
        clean_dir=clean_dir,
        output_zip=output_zip,
        trigger_word=trigger_word,
        rank=rank,
        steps=steps,
        save_every=save_every,
    )


@app.command()
def train(
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to clean training images"),
    trigger_word: str = typer.Option("rexstyle", help="LoRA trigger word"),
    steps: int = typer.Option(1000, help="Training steps (e.g. 1000)"),
    lr: float = typer.Option(0.0008, help="Learning rate"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip cost confirmation prompt"),
):
    """Optional Paid Mode: Zips dataset/clean, displays cost estimate, and runs LoRA training on fal.ai."""
    from src.train_lora import train_flux_lora
    try:
        train_flux_lora(
            clean_dir=clean_dir,
            trigger_word=trigger_word,
            is_style=True,
            steps=steps,
            learning_rate=lr,
            auto_confirm=yes,
        )
    except RuntimeError:
        raise typer.Exit(code=1)


@app.command("train-local")
def train_local(
    clean_dir: Path = typer.Option(Path("dataset/clean"), help="Path to clean training images"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override base architecture: 'sd15' or 'sdxl' (default: auto-detected from VRAM)"),
    steps: int = typer.Option(1200, help="Training steps (default: 1200)"),
    rank: int = typer.Option(16, help="LoRA network rank (dim)"),
    lr: float = typer.Option(1e-4, help="Learning rate"),
    optimizer: str = typer.Option("AdamW8bit", "--optimizer", "-o", help="Optimizer: 'AdamW8bit' or 'Adafactor'"),
    save_every: int = typer.Option(250, help="Checkpoint frequency in steps"),
    output_name: str = typer.Option("rexstyle_lora", help="Output model name"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print command and setup without starting training"),
):
    """Local LoRA training on NVIDIA GPU. Auto-selects SD 1.5 for <=6GB VRAM with SDPA & AdamW8bit."""
    from src.local_trainer import run_local_training
    try:
        run_local_training(
            clean_dir=clean_dir,
            output_name=output_name,
            model_override=model,
            steps=steps,
            save_every=save_every,
            rank=rank,
            lr=lr,
            optimizer_type=optimizer,
            dry_run=dry_run,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]Training Setup Error:[/bold red] {e}")
        raise typer.Exit(code=1)



@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for the post (e.g. 'Distributed Systems')"),
    lora: Optional[Path] = typer.Option(None, "--lora", help="Path to local .safetensors LoRA file (requires CUDA GPU)"),
    local_lora: Optional[Path] = typer.Option(None, "--local-lora", help="Alias for --lora"),
    backend: str = typer.Option("fallback", "--backend", "-b", help="Backend: 'fallback' (free), 'local' (diffusers), 'fal' (optional paid)"),
    scale: float = typer.Option(1.0, "--scale", "-s", help="LoRA adaptation scale (default 1.0, test 0.8 too)"),
    lora_url: Optional[str] = typer.Option(None, help="Hosted LoRA safetensors URL (for fal backend)"),
    layout: str = typer.Option("headline-on-photo", help="Layout: headline-on-photo, photo-only, quote-card"),
    count: int = typer.Option(3, help="Number of candidates to generate"),
):
    """Generates candidate images. Defaults to free fallback; supports local diffusers (SD 1.5/SDXL) and paid fal.ai."""
    pw = PromptWriter(BRAND_CONFIG, STYLE_GUIDE_PATH)
    prompt_obj = pw.build_prompt_with_llm(topic, layout_type=layout)

    console.print(f"[bold]Generated Headline:[/bold] {prompt_obj.headline}")
    console.print(f"[bold]Flux Prompt:[/bold] {prompt_obj.positive_prompt}\n")

    chosen_lora = lora or local_lora
    try:
        candidates = generate_candidates(
            prompt=prompt_obj.positive_prompt,
            headline=prompt_obj.headline,
            backend=backend,
            local_lora_path=chosen_lora,
            lora_url=lora_url,
            lora_scale=scale,
            num_candidates=count,
        )
        for c in candidates:
            console.print(f"  -> Candidate: [green]{c}[/green]")
    except (RuntimeError, ValueError) as e:
        console.print(f"[bold red]Generation Error:[/bold red] {e}")
        raise typer.Exit(code=1)



@app.command()
def compare(
    scale: float = typer.Option(1.0, "--scale", "-s", help="LoRA scale for comparison (e.g. 1.0 or 0.8)"),
    lora_url: Optional[str] = typer.Option(None, help="Explicit LoRA URL (defaults to config/lora.json)"),
    backend: str = typer.Option("fallback", "--backend", "-b", help="Backend: 'fallback' (free) or 'fal' (paid)"),
):
    """Generates identical 3 benchmark prompts side-by-side (With LoRA vs Without LoRA)."""
    from src.compare import run_comparison
    run_comparison(lora_url=lora_url, lora_scale=scale, force_fallback=(backend == "fallback"))


@app.command()
def check(
    image: Path = typer.Argument(..., help="Path to generated image to evaluate"),
):
    """Runs Vision LLM quality gate scoring against brand aesthetic criteria."""
    console.print(f"[cyan]Evaluating image quality for {image}...[/cyan]")
    score = evaluate_image(image)
    print_quality_report(image.name, score)


@app.command()
def overlay(
    image: Path = typer.Argument(..., help="Path to image file"),
    headline: str = typer.Option(..., "--headline", "-h", help="Headline text to render"),
    layout: str = typer.Option("headline-on-photo", help="Layout: headline-on-photo, photo-only, quote-card"),
    zone: str = typer.Option("top", help="Negative space zone: top or bottom"),
    output: Optional[Path] = typer.Option(None, help="Output image path"),
):
    """Overlays brand typography onto an image."""
    engine = TypographyEngine(BRAND_CONFIG)
    img = Image.open(image)
    overlaid = engine.apply_overlay(img, headline=headline, layout_type=layout, text_zone=zone)

    if output is None:
        output = Path("outputs/drafts") / f"overlay_{image.name}"
    output.parent.mkdir(parents=True, exist_ok=True)
    overlaid.save(output, "JPEG", quality=95)
    console.print(f"[bold green][OK] Overlaid image saved to: {output}[/bold green]")


@app.command()
def export(
    image: Path = typer.Argument(..., help="Path to image to export"),
    output_dir: Path = typer.Option(Path("outputs/drafts"), help="Output directory"),
    name: str = typer.Option("post", help="Base name for exported files"),
):
    """Exports image into 1080x1350 (portrait), 1080x1080 (square), and 1200x627 (landscape)."""
    results = export_single_post(image, output_dir=output_dir, base_name=name)
    console.print("[bold green][OK] Exported files:[/bold green]")
    for fmt, p in results.items():
        size_kb = os.path.getsize(p) / 1024
        console.print(f"  [{fmt}] {p} ({size_kb:.1f} KB)")


@app.command()
def carousel(
    images: list[Path] = typer.Argument(..., help="Image paths in slide order"),
    output: Path = typer.Option(Path("outputs/drafts/carousel.pdf"), help="Output PDF path"),
):
    """Combines multiple slide images into a multi-page PDF carousel."""
    pdf_path = create_carousel_pdf(images, output_path=output)
    console.print(f"[bold green][OK] Carousel PDF exported to: {pdf_path}[/bold green]")


@app.command("create-basic")
def create_basic(
    topic: str = typer.Option("Architecting Resilient Distributed Systems", "--topic", "-t"),
    layout: str = typer.Option("headline-on-photo", help="headline-on-photo | photo-only | quote-card"),
    fallback: bool = typer.Option(False, "--fallback", help="Force fallback generation"),
):
    """End-to-End Phase 1 Flow: Prompts -> Generates -> Evaluates -> Overlays -> Exports."""
    console.print(f"[bold blue]=== Starting Phase 1 Visual Production Flow for: '{topic}' ===[/bold blue]\n")

    # 1. Prompt Writing
    console.print("[bold cyan]Step 1: Formulating on-brand Flux prompt...[/bold cyan]")
    pw = PromptWriter(BRAND_CONFIG, STYLE_GUIDE_PATH)
    prompt_obj = pw.build_prompt_with_llm(topic, layout_type=layout)
    console.print(f"  Headline: [green]{prompt_obj.headline}[/green]")
    console.print(f"  Prompt: [dim]{prompt_obj.positive_prompt}[/dim]\n")

    # 2. Generation at 1024x1280
    console.print("[bold cyan]Step 2: Generating raw image at 1024x1280 (4:5)...[/bold cyan]")
    candidates = generate_candidates(
        prompt=prompt_obj.positive_prompt,
        num_candidates=1,
        width=1024,
        height=1280,
        force_fallback=fallback,
    )
    raw_image_path = candidates[0]
    console.print(f"  Raw candidate saved: [green]{raw_image_path}[/green]\n")

    # 3. Quality Gate Check
    console.print("[bold cyan]Step 3: Running Vision LLM Quality Check...[/bold cyan]")
    score = evaluate_image(raw_image_path)
    print_quality_report(raw_image_path.name, score)

    # 4. Typography Overlay
    console.print("[bold cyan]Step 4: Applying Typography Engine overlay...[/bold cyan]")
    engine = TypographyEngine(BRAND_CONFIG)
    img = Image.open(raw_image_path)
    overlaid = engine.apply_overlay(
        img,
        headline=prompt_obj.headline,
        layout_type=layout,
        text_zone=score.recommended_text_zone if score.recommended_text_zone in ("top", "bottom") else "top",
    )
    draft_path = Path("outputs/drafts") / f"draft_{raw_image_path.name}"
    overlaid.save(draft_path, "JPEG", quality=95)
    console.print(f"  Overlaid composite saved: [green]{draft_path}[/green]\n")

    # 5. Export to 1080x1350
    console.print("[bold cyan]Step 5: Exporting final standard LinkedIn formats...[/bold cyan]")
    exports = export_single_post(overlaid, output_dir=Path("outputs/drafts"), base_name=f"final_{raw_image_path.stem}")
    for fmt, p in exports.items():
        size_kb = os.path.getsize(p) / 1024
        console.print(f"  [bold green][OK] {fmt.upper()}:[/bold green] {p} ({size_kb:.1f} KB)")

    console.print(f"\n[bold green][SUCCESS] Phase 1 pipeline executed end-to-end![/bold green]")
    console.print(f"Primary LinkedIn Portrait ready for posting: [bold white]{exports['portrait']}[/bold white]\n")


if __name__ == "__main__":
    app()
