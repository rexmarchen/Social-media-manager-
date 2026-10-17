"""
tests/test_phase2.py - Unit tests for Phase 2 components: LoRA packaging, cost estimation, and comparison stitching.
"""

import tempfile
from pathlib import Path
from PIL import Image

from src.train_lora import create_training_zip, estimate_training_cost
from src.compare import create_side_by_side


def test_cost_estimation():
    cost_1000 = estimate_training_cost(1000)
    assert 2.0 <= cost_1000 <= 2.5
    cost_500 = estimate_training_cost(500)
    assert 1.0 <= cost_500 <= 1.3


def test_create_training_zip():
    with tempfile.TemporaryDirectory() as tmpdir:
        clean_dir = Path(tmpdir) / "clean"
        clean_dir.mkdir()

        # Create dummy pairs
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img.save(clean_dir / "sample_1.jpg")
        with open(clean_dir / "sample_1.txt", "w") as f:
            f.write("rexstyle, test sample description")

        zip_dest = Path(tmpdir) / "dataset.zip"
        res_zip = create_training_zip(clean_dir, zip_dest)
        assert res_zip.exists()
        assert res_zip.stat().st_size > 0


def test_create_side_by_side():
    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Image.new("RGB", (1024, 1280), color=(200, 50, 50))
        img2 = Image.new("RGB", (1024, 1280), color=(50, 50, 200))

        p1 = Path(tmpdir) / "no_lora.jpg"
        p2 = Path(tmpdir) / "with_lora.jpg"
        img1.save(p1)
        img2.save(p2)

        out_stitched = Path(tmpdir) / "stitched.jpg"
        result = create_side_by_side(
            no_lora_path=p1,
            lora_path=p2,
            output_path=out_stitched,
            prompt_title="Test Benchmark",
            lora_scale=1.0,
        )

        assert result.exists()
        with Image.open(result) as stitched_img:
            # Width should be 2 * 1024 + borders = 2108
            assert stitched_img.size[0] > 2048
            assert stitched_img.size[1] > 1280


def test_export_training_kit_bundle():
    from src.training_kit import export_training_kit_bundle
    with tempfile.TemporaryDirectory() as tmpdir:
        clean_dir = Path(tmpdir) / "clean"
        clean_dir.mkdir()

        # Dummy sample
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img.save(clean_dir / "sample.jpg")
        with open(clean_dir / "sample.txt", "w") as f:
            f.write("rexstyle, test prompt")

        out_zip = Path(tmpdir) / "training_kit.zip"
        nb_dir = Path(tmpdir) / "notebooks"
        guide_p = Path(tmpdir) / "TRAINING_GUIDE.md"

        res = export_training_kit_bundle(
            clean_dir=clean_dir,
            output_zip=out_zip,
            notebook_dir=nb_dir,
            guide_path=guide_p,
        )

        assert res["zip"].exists()
        assert res["notebook"].exists()
        assert res["guide"].exists()


def test_local_diffusers_no_gpu_error():
    import pytest
    from src.generate import generate_with_diffusers_local
    with pytest.raises(RuntimeError, match="CUDA GPU is required"):
        generate_with_diffusers_local(
            prompt="rexstyle test",
            local_lora_path=Path("models/dummy.safetensors"),
        )
