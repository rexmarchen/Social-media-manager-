"""
local_trainer.py - Local LoRA training for NVIDIA GPUs (RTX 3050 4GB / 6GB / 8GB).
Features:
- Auto-detects GPU VRAM and chooses SD 1.5 (<=6GB) or SDXL (>=8GB)
- Verifies PyTorch CUDA at startup and halts clearly if CUDA is False
- Uses PyTorch built-in SDPA attention (--sdpa) instead of xformers
- Low-VRAM flags: AdamW8bit, fp16, gradient checkpointing, cached latents, batch 1
- Windows stability: --caption_extension=.txt, --save_model_as=safetensors, --max_data_loader_n_workers=0, --seed=42
- Aspect-ratio bucketing (--enable_bucket with 512 base)
- Monitors Kohya subprocess output for OOM and bnb failure
- Saves trained weights into ./models/
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from rich.console import Console
from rich.panel import Panel

console = Console()

SD15_MODEL_REPO = "stable-diffusion-v1-5/stable-diffusion-v1-5"
SDXL_MODEL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"


def inspect_gpu() -> Tuple[bool, str, float]:
    """
    Checks for available CUDA GPU via torch.cuda or nvidia-smi.
    Returns: (is_available, gpu_name, vram_gb)
    """
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            total_bytes = torch.cuda.get_device_properties(0).total_memory
            vram_gb = total_bytes / (1024 ** 3)
            return True, name, round(vram_gb, 2)
    except Exception:
        pass

    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        )
        line = smi.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        name = parts[0]
        vram_mb = float(parts[1])
        vram_gb = vram_mb / 1024.0
        return True, name, round(vram_gb, 2)
    except Exception:
        pass

    return False, "None", 0.0


def select_model_architecture(vram_gb: float, override: Optional[str] = None) -> Tuple[str, str, int]:
    """
    Selects base model and training resolution based on VRAM.
    Returns: (arch_type: 'sd15' | 'sdxl', model_repo, base_resolution)
    """
    if override:
        chosen = override.lower()
        if chosen in ("sd15", "sd1.5", "v1-5", "sd-1.5"):
            return "sd15", SD15_MODEL_REPO, 512
        elif chosen in ("sdxl", "xl"):
            return "sdxl", SDXL_MODEL_REPO, 768
        raise ValueError(f"Unknown model override '{override}'. Choose 'sd15' or 'sdxl'.")

    # Auto-detection: <= 6.5 GB VRAM -> SD 1.5, >= 7 GB -> SDXL
    if vram_gb <= 6.5:
        return "sd15", SD15_MODEL_REPO, 512
    else:
        return "sdxl", SDXL_MODEL_REPO, 768


def prepare_kohya_dataset_dir(clean_dir: Path, target_dir: Path, repeats: int = 10, trigger_word: str = "rexstyle") -> Path:
    """
    Stages clean images and captions into Kohya dataset folder structure:
    target_dir / img / <repeats>_<trigger_word> / <files>
    """
    clean_dir = Path(clean_dir)
    target_dir = Path(target_dir)

    subset_dir = target_dir / "img" / f"{repeats}_{trigger_word}"
    subset_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for p in clean_dir.iterdir():
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".txt"):
            dest = subset_dir / p.name
            shutil.copy2(p, dest)
            copied += 1

    console.print(f"[dim]Staged {copied} training files in {subset_dir}[/dim]")
    return target_dir / "img"


def build_kohya_training_command(
    scripts_dir: Path,
    arch_type: str,
    model_repo: str,
    train_data_dir: Path,
    output_dir: Path,
    output_name: str,
    resolution: int = 512,
    rank: int = 16,
    steps: int = 1200,
    save_every: int = 250,
    lr: float = 1e-4,
    optimizer_type: str = "AdamW8bit",
) -> list[str]:
    """
    Constructs the exact Kohya sd-scripts command with strict low-VRAM optimizations:
    --sdpa, AdamW8bit, fp16, gradient_checkpointing, cache_latents, enable_bucket,
    --caption_extension=.txt, --save_model_as=safetensors, --max_data_loader_n_workers=0, --seed=42
    """
    script_name = "train_network.py" if arch_type == "sd15" else "sdxl_train_network.py"
    script_path = scripts_dir / script_name

    cmd = [
        sys.executable,
        str(script_path),
        f"--pretrained_model_name_or_path={model_repo}",
        f"--train_data_dir={train_data_dir}",
        f"--output_dir={output_dir}",
        f"--output_name={output_name}",
        f"--caption_extension=.txt",
        "--save_model_as=safetensors",
        "--max_data_loader_n_workers=0",
        "--seed=42",
        f"--resolution={resolution},{resolution}",
        f"--max_train_steps={steps}",
        f"--save_every_n_steps={save_every}",
        "--train_batch_size=1",
        "--network_module=networks.lora",
        f"--network_dim={rank}",
        f"--network_alpha={rank}",
        f"--learning_rate={lr}",
        f"--optimizer_type={optimizer_type}",
        "--lr_scheduler=cosine",
        "--mixed_precision=fp16",
        "--save_precision=fp16",
        "--gradient_checkpointing",
        "--cache_latents",
        "--enable_bucket",
        f"--min_bucket_reso={max(256, resolution - 128)}",
        f"--max_bucket_reso={min(1024, resolution + 256)}",
        "--sdpa",  # PyTorch built-in SDPA attention (no xformers package needed)
        "--network_train_unet_only",  # Saves VRAM on 4GB GPUs by skipping text-encoder training
        "--keep_tokens=1",  # Keeps trigger word (rexstyle) pinned as the first token
        "--shuffle_caption",  # Shuffles remaining caption tokens for superior style generalization
    ]
    return cmd


def execute_kohya_subprocess(cmd: list[str]) -> Tuple[int, str]:
    """
    Executes the Kohya subprocess, streaming output in real-time and capturing logs
    to diagnose OOM errors and optimizer initialization failures.
    """
    captured_lines = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    if proc.stdout:
        for line in iter(proc.stdout.readline, ""):
            print(line, end="")
            captured_lines.append(line)
        proc.stdout.close()

    return_code = proc.wait()
    full_log = "".join(captured_lines)
    return return_code, full_log


def run_local_training(
    clean_dir: Path = Path("dataset/clean"),
    models_dir: Path = Path("models"),
    output_name: str = "rexstyle_lora",
    model_override: Optional[str] = None,
    steps: int = 1200,
    save_every: int = 250,
    rank: int = 16,
    lr: float = 1e-4,
    optimizer_type: str = "AdamW8bit",
    scripts_dir: Path = Path("sd-scripts"),
    dry_run: bool = False,
) -> Dict:
    """
    Orchestrates local LoRA training on NVIDIA GPU.
    Checks hardware, auto-selects SD 1.5 or SDXL, runs Kohya, and handles OOM fallbacks.
    """
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # 1. Startup verification of PyTorch and CUDA
    torch_version = "not installed"
    cuda_available = False
    try:
        import torch
        torch_version = torch.__version__
        cuda_available = torch.cuda.is_available()
    except Exception as e:
        torch_version = f"Error: {e}"

    console.print(f"[bold]PyTorch Version:[/bold] {torch_version}")
    console.print(f"[bold]CUDA Available:[/bold] {cuda_available}")

    if not cuda_available:
        console.print(
            Panel(
                f"[bold red]CUDA is not available in current PyTorch![/bold red]\n\n"
                f"Installed PyTorch version: {torch_version}\n"
                f"CUDA Available: {cuda_available}\n\n"
                "To train locally on your RTX 3050 GPU, install PyTorch with CUDA:\n"
                "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121\n\n"
                "See SETUP_LOCAL.md for full instructions.",
                title="CUDA Verification Notice",
                border_style="yellow" if dry_run else "red",
            )
        )
        if not dry_run:
            raise RuntimeError(f"PyTorch with CUDA is required for train-local, but got {torch_version} with cuda={cuda_available}.")
        console.print("[dim yellow](Proceeding in dry-run mode to display generated training command)[/dim yellow]\n")


    # 2. Inspect Hardware
    has_gpu, gpu_name, vram_gb = inspect_gpu()
    arch_type, model_repo, resolution = select_model_architecture(vram_gb, override=model_override)

    # Check for OneDrive location warning
    cwd_str = str(Path.cwd()).lower()
    if "onedrive" in cwd_str:
        console.print(
            Panel(
                "[bold yellow]WARNING: Your project is located inside Microsoft OneDrive![/bold yellow]\n"
                "OneDrive will continuously attempt to sync checkpoints, which can lock files and slow down training.\n"
                "We strongly recommend moving your training folder to a local path (e.g., C:\\ai\\linkedin-image-agent).",
                title="OneDrive Sync Warning",
                border_style="yellow",
            )
        )

    console.print(
        Panel(
            f"[bold]Detected GPU:[/bold] {gpu_name} ({vram_gb:.1f} GB Dedicated VRAM)\n"
            f"[bold]Selected Architecture:[/bold] {arch_type.upper()} ({model_repo})\n"
            f"[bold]Base Resolution:[/bold] {resolution}x{resolution} with --enable_bucket\n"
            f"[bold]LoRA Rank (Dim):[/bold] {rank}\n"
            f"[bold]Steps:[/bold] {steps} (Save checkpoint every {save_every} steps)\n"
            f"[bold]Optimizer:[/bold] {optimizer_type}\n"
            f"[bold]Attention Mechanism:[/bold] PyTorch SDPA (--sdpa)\n"
            f"[bold]Stability Flags:[/bold] --caption_extension=.txt, --save_model_as=safetensors, --max_data_loader_n_workers=0, --seed=42",
            title="Local Training Configuration",
            border_style="cyan",
        )
    )

    # 3. Stage dataset
    staged_dir = Path("outputs/kohya_staging")
    train_data_dir = prepare_kohya_dataset_dir(clean_dir, staged_dir, repeats=10, trigger_word="rexstyle")

    # Build Command
    cmd = build_kohya_training_command(
        scripts_dir=scripts_dir,
        arch_type=arch_type,
        model_repo=model_repo,
        train_data_dir=train_data_dir,
        output_dir=models_dir,
        output_name=output_name,
        resolution=resolution,
        rank=rank,
        steps=steps,
        save_every=save_every,
        lr=lr,
        optimizer_type=optimizer_type,
    )

    console.print(f"\n[bold]Generated Training Command:[/bold]\n[dim]{' '.join(cmd)}[/dim]\n")

    if dry_run:
        console.print("[yellow]Dry-run mode: Training command generated and dataset staged without execution.[/yellow]")
        return {"status": "dry_run", "command": cmd, "arch": arch_type, "model": model_repo}

    # 4. Check if kohya scripts exist for execution
    if not scripts_dir.exists():
        console.print(
            Panel(
                f"[bold red]Kohya sd-scripts directory not found at: {scripts_dir}[/bold red]\n\n"
                f"Please clone the repository:\n"
                f"  git clone https://github.com/kohya-ss/sd-scripts.git\n"
                f"  pip install -r sd-scripts/requirements.txt\n\n"
                f"See SETUP_LOCAL.md for full instructions.",
                title="Missing Training Scripts",
                border_style="red",
            )
        )
        raise FileNotFoundError(f"Kohya scripts directory not found: {scripts_dir}")

    # 5. Execute Training with Process Output Inspection (OOM & bitsandbytes checks)
    console.print("[bold green]Starting local training run...[/bold green]")
    code, log = execute_kohya_subprocess(cmd)

    if code != 0:
        console.print(f"[bold red]Training process exited with error code {code}.[/bold red]")

        # Check for bitsandbytes failure
        if "bitsandbytes" in log.lower() or "adamw8bit" in log.lower():
            console.print(
                Panel(
                    "[bold red]AdamW8bit failed to initialize on your system![/bold red]\n\n"
                    "bitsandbytes encountered an initialization or CUDA loading error.\n"
                    "You can retry using Adafactor (low memory, no bitsandbytes required):\n\n"
                    f"  python -m src.cli train-local --optimizer Adafactor",
                    title="Optimizer Initialization Error",
                    border_style="red",
                )
            )
            raise RuntimeError("AdamW8bit failed to load. Retry with --optimizer Adafactor.")

        # Check for CUDA OOM
        if "out of memory" in log.lower() or "outofmemoryerror" in log.lower():
            console.print(
                Panel(
                    "[bold yellow]CUDA Out-Of-Memory detected in Kohya process output![/bold yellow]\n\n"
                    f"Attempting Automatic Low-VRAM Recovery:\n"
                    f"- Reducing LoRA rank from {rank} -> 8\n"
                    f"- Reducing resolution from {resolution} -> {max(384, resolution - 64)}\n"
                    f"- Retaining the same model architecture ({arch_type.upper()}). No silent model swap.",
                    title="OOM Recovery",
                    border_style="yellow",
                )
            )
            recovery_cmd = build_kohya_training_command(
                scripts_dir=scripts_dir,
                arch_type=arch_type,
                model_repo=model_repo,
                train_data_dir=train_data_dir,
                output_dir=models_dir,
                output_name=f"{output_name}_rank8",
                resolution=max(384, resolution - 64),
                rank=8,
                steps=steps,
                save_every=save_every,
                lr=lr,
                optimizer_type=optimizer_type,
            )
            console.print(f"[dim]Running recovery command: {' '.join(recovery_cmd)}[/dim]")
            code, log = execute_kohya_subprocess(recovery_cmd)
            if code != 0:
                raise RuntimeError(f"Training failed after OOM recovery attempt. Exit code: {code}")

    final_model_path = models_dir / f"{output_name}.safetensors"
    console.print(f"[bold green][OK] Training complete. Model weights saved to {final_model_path}[/bold green]")
    return {"status": "success", "arch": arch_type, "model_path": final_model_path}
