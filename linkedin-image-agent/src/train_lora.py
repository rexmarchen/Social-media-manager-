"""
train_lora.py - Trains a FLUX.1 LoRA style adapter on fal.ai.
Zips dataset/clean/, uploads to fal storage, calls fal-ai/flux-lora-fast-training,
polls logs until completion, saves to config/lora.json, and downloads local .safetensors.
"""

from __future__ import annotations

import json
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict
import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

COST_PER_STEP = 0.0022  # ~$2.20 per 1,000 steps


def create_training_zip(clean_dir: Path, zip_output_path: Path) -> Path:
    """Creates a zip file containing paired .jpg and .txt training files."""
    clean_dir = Path(clean_dir)
    zip_output_path = Path(zip_output_path)
    zip_output_path.parent.mkdir(parents=True, exist_ok=True)

    files_to_zip = []
    for p in clean_dir.iterdir():
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".txt"):
            files_to_zip.append(p)

    if not files_to_zip:
        raise ValueError(f"No training files found in {clean_dir}.")

    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_zip:
            zf.write(f, arcname=f.name)

    size_mb = os.path.getsize(zip_output_path) / (1024 * 1024)
    console.print(f"[green]Packaged {len(files_to_zip)} training files into {zip_output_path} ({size_mb:.2f} MB)[/green]")
    return zip_output_path


def estimate_training_cost(steps: int = 1000) -> float:
    """Returns estimated cost in USD based on fal.ai pricing."""
    return round(steps * COST_PER_STEP, 2)


def train_flux_lora(
    clean_dir: Path = Path("dataset/clean"),
    trigger_word: str = "rexstyle",
    is_style: bool = True,
    steps: int = 1000,
    learning_rate: float = 0.0008,
    output_config: Path = Path("config/lora.json"),
    models_dir: Path = Path("models"),
    auto_confirm: bool = False,
) -> Dict:
    """Executes the complete fal.ai LoRA fast training job."""
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        console.print(
            Panel(
                "[bold red]FAL_KEY is missing![/bold red]\n\n"
                "To train a LoRA on fal.ai, you must set FAL_KEY in your .env file.\n"
                "Get your key at: https://fal.ai/dashboard/keys",
                title="Authentication Error",
                border_style="red",
            )
        )
        raise RuntimeError("FAL_KEY environment variable is not configured.")

    import fal_client

    # 1. Cost estimation and confirmation
    cost = estimate_training_cost(steps)
    console.print(
        Panel(
            f"[bold]Target Endpoint:[/bold] fal-ai/flux-lora-fast-training\n"
            f"[bold]Trigger Word:[/bold] {trigger_word}\n"
            f"[bold]Style Mode (`is_style`):[/bold] {is_style}\n"
            f"[bold]Training Steps:[/bold] {steps}\n"
            f"[bold]Learning Rate:[/bold] {learning_rate}\n"
            f"[bold yellow]Estimated Cost:[/bold yellow] ~${cost:.2f} USD (~{steps} steps)",
            title="LoRA Training Job Summary",
            border_style="cyan",
        )
    )

    if not auto_confirm:
        confirm = console.input("\n[bold yellow]Do you want to proceed with submitting this training job to fal.ai? (y/N): [/bold yellow]").strip().lower()
        if confirm not in ("y", "yes"):
            console.print("[yellow]Training job cancelled by user.[/yellow]")
            return {"status": "cancelled"}

    # 2. Package dataset into ZIP
    zip_path = Path("outputs/dataset.zip")
    create_training_zip(clean_dir, zip_path)

    # 3. Upload dataset to fal storage
    console.print("[cyan]Uploading dataset to fal.ai storage...[/cyan]")
    dataset_url = fal_client.upload_file(str(zip_path))
    console.print(f"[green]Dataset uploaded to: {dataset_url}[/green]")

    # 4. Submit training job
    console.print("[bold cyan]Submitting training job to fal-ai/flux-lora-fast-training...[/bold cyan]")
    arguments = {
        "images_data_url": dataset_url,
        "trigger_word": trigger_word,
        "is_style": is_style,
        "steps": steps,
        "learning_rate": learning_rate,
    }

    def on_queue_update(update):
        if hasattr(update, "logs") and update.logs:
            for log in update.logs:
                console.print(f"[dim]{log.get('message', '')}[/dim]")

    result = fal_client.subscribe(
        "fal-ai/flux-lora-fast-training",
        arguments=arguments,
        with_logs=True,
        on_enqueue=lambda q: console.print(f"[cyan]Enqueued job. Position: {getattr(q, 'queue_position', 'processing')}[/cyan]"),
    )

    console.print("[bold green]LoRA training successfully finished![/bold green]")

    diffusers_file = result.get("diffusers_lora_file", {})
    lora_url = diffusers_file.get("url")
    if not lora_url:
        # Fallback key check
        lora_url = result.get("lora_url") or result.get("output", {}).get("url")

    # 5. Save config/lora.json
    output_config = Path(output_config)
    output_config.parent.mkdir(parents=True, exist_ok=True)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    local_safetensors_path = models_dir / f"{trigger_word}_lora_{steps}steps.safetensors"

    metadata = {
        "trigger_word": trigger_word,
        "is_style": is_style,
        "steps": steps,
        "learning_rate": learning_rate,
        "lora_url": lora_url,
        "local_path": str(local_safetensors_path),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_details": result,
    }

    with open(output_config, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    console.print(f"[bold green]Saved LoRA configuration to {output_config}[/bold green]")

    # 6. Download .safetensors locally
    if lora_url:
        console.print(f"[cyan]Downloading weights to {local_safetensors_path}...[/cyan]")
        resp = httpx.get(lora_url, timeout=120.0, follow_redirects=True)
        if resp.status_code == 200:
            with open(local_safetensors_path, "wb") as f:
                f.write(resp.content)
            size_mb = os.path.getsize(local_safetensors_path) / (1024 * 1024)
            console.print(f"[bold green][OK] LoRA safetensors downloaded ({size_mb:.1f} MB) to: {local_safetensors_path}[/bold green]")

    return metadata
