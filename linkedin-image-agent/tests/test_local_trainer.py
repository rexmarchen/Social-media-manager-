"""
tests/test_local_trainer.py - Unit tests for local trainer GPU detection, architecture selection, and command building.
"""

from pathlib import Path
from src.local_trainer import select_model_architecture, build_kohya_training_command
from src.generate import detect_lora_architecture


def test_select_model_architecture_vram_auto():
    # 4.0 GB RTX 3050 -> SD 1.5
    arch, repo, res = select_model_architecture(4.0)
    assert arch == "sd15"
    assert "stable-diffusion-v1-5" in repo
    assert res == 512

    # 6.0 GB -> SD 1.5
    arch6, repo6, res6 = select_model_architecture(6.0)
    assert arch6 == "sd15"
    assert res6 == 512

    # 8.0 GB -> SDXL
    arch8, repo8, res8 = select_model_architecture(8.0)
    assert arch8 == "sdxl"
    assert "xl" in repo8.lower()
    assert res8 == 768


def test_select_model_architecture_override():
    arch, repo, res = select_model_architecture(4.0, override="sdxl")
    assert arch == "sdxl"
    assert res == 768

    arch2, repo2, res2 = select_model_architecture(16.0, override="sd15")
    assert arch2 == "sd15"
    assert res2 == 512


def test_build_kohya_training_command_sdpa_and_bucket():
    cmd = build_kohya_training_command(
        scripts_dir=Path("sd-scripts"),
        arch_type="sd15",
        model_repo="stable-diffusion-v1-5/stable-diffusion-v1-5",
        train_data_dir=Path("outputs/dataset"),
        output_dir=Path("models"),
        output_name="rexstyle_test",
        resolution=512,
        rank=16,
        steps=1200,
        save_every=250,
    )

    cmd_str = " ".join(cmd)
    assert "--sdpa" in cmd_str
    assert "--enable_bucket" in cmd_str
    assert "--optimizer_type=AdamW8bit" in cmd_str
    assert "--gradient_checkpointing" in cmd_str
    assert "--cache_latents" in cmd_str
    assert "--caption_extension=.txt" in cmd_str
    assert "--save_model_as=safetensors" in cmd_str
    assert "--max_data_loader_n_workers=0" in cmd_str
    assert "--seed=42" in cmd_str
    assert "--network_train_unet_only" in cmd_str
    assert "--keep_tokens=1" in cmd_str
    assert "--shuffle_caption" in cmd_str
    assert "train_network.py" in cmd_str


def test_detect_lora_architecture():
    sd15_name = Path("models/rexstyle_sd15_lora.safetensors")
    sdxl_name = Path("models/rexstyle_sdxl_lora.safetensors")

    assert detect_lora_architecture(sd15_name) == "sd15"
    assert detect_lora_architecture(sdxl_name) == "sdxl"
