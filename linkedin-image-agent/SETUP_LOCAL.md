# Local LoRA Training & Inference Setup (Windows RTX 3050 4GB)

This guide walks you through setting up and running **100% free local LoRA training** on your **NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM)** using PyTorch with CUDA, PyTorch's native SDPA attention, and Kohya-ss `sd-scripts`.

---

## 0. Critical First Step: Move Project Outside OneDrive

Your current project path is located inside `OneDrive`:
`C:\Users\anshupal\OneDrive\Documents\linkdin automation`

> [!WARNING]
> Training neural networks writes thousands of state files and large `.safetensors` checkpoints. **OneDrive will attempt to sync these files continuously**, which causes file locks, memory spikes, and severe training slowdowns.
> 
> **Recommendation:** Copy or move the `linkedin-image-agent` directory to a non-synced local folder, for example:
> ```powershell
> # Open PowerShell and copy project:
> mkdir C:\ai
> Copy-Item -Recurse "C:\Users\anshupal\OneDrive\Documents\linkdin automation\linkedin-image-agent" "C:\ai\linkedin-image-agent"
> cd C:\ai\linkedin-image-agent
> ```

---

## 1. Create a Clean Python Virtual Environment

To avoid version conflicts with other installed tools:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 2. Install PyTorch with CUDA 12.1 / 12.4

Your NVIDIA driver `610.47` supports modern CUDA runtimes. Install the official CUDA-enabled PyTorch build:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Verify CUDA is active:
```powershell
python -c "import torch; print('CUDA Available:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0))"
```
*(Must output `CUDA Available: True | GPU: NVIDIA GeForce RTX 3050 Laptop GPU`)*

---

## 3. Install Core Low-VRAM & Training Dependencies

Install native Windows wheels for `bitsandbytes` (8-bit AdamW optimizer), Hugging Face `diffusers`, and `accelerate`:

```powershell
pip install "bitsandbytes>=0.43.3" accelerate diffusers transformers safetensors
pip install -r requirements.txt
```

---

## 4. Clone Kohya-ss `sd-scripts` & Re-check CUDA

Clone the official `sd-scripts` repository into your project root:

```powershell
git clone https://github.com/kohya-ss/sd-scripts.git
pip install -r sd-scripts/requirements.txt
```

### ⚠️ Re-check CUDA (Critical Step)
Installing `sd-scripts/requirements.txt` can sometimes replace your CUDA PyTorch build with a CPU-only build. Run this immediately:

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

- **Required Output:** Must print `True` and a version ending in `+cu121` (or your installed CUDA version, e.g. `2.4.1+cu121 True`).
- **If it prints `False` or has `+cpu`:** Reinstall the CUDA build immediately:
  ```powershell
  pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu121
  ```

---

## 4.1 Pre-Launch System Checklist

Before starting training, perform these quick checks:
1. **CUDA PyTorch:** Verified with `torch.cuda.is_available()` returning `True`.
2. **Accelerate Config (if needed):** If Kohya complains about missing accelerate config, run:
   ```powershell
   accelerate config
   ```
   *(Select: `This machine`, `No distributed training`, `GPU 0`, `fp16`)*
3. **Free Disk Space:** Ensure at least ~15 GB free on drive `C:` for caches and checkpoints.
4. **GPU Idle Check:** Run `nvidia-smi` in PowerShell — make sure GPU memory usage is under ~300 MB before training (close Chrome/Discord if needed).
5. **Power Mode:** Plug your laptop into the charger and set Windows Power Mode to **Best performance**.

## 5. Training Configuration (Tuned for 4 GB VRAM)

Your RTX 3050 has 4 GB VRAM. Training is tuned to run within **~3.4 GB VRAM**:

| Parameter | Setting | Reason |
| :--- | :--- | :--- |
| **Base Model** | `stable-diffusion-v1-5/stable-diffusion-v1-5` | Verified active HuggingFace mirror (fits 4 GB) |
| **Attention** | `--sdpa` | PyTorch native scaled dot-product attention (avoids xformers bugs) |
| **Optimizer** | `AdamW8bit` (`bitsandbytes`) | Cuts optimizer VRAM footprint in half |
| **Precision** | `fp16` mixed & save precision | Halves activation memory |
| **Resolution** | `512,512` with `--enable_bucket` | Fits portrait 4:5 photos without harsh cropping |
| **Memory Flags** | `--gradient_checkpointing --cache_latents` | Pre-caches VAE latents; keeps VRAM < 3.5 GB |
| **UNet Only** | `--network_train_unet_only` | Skips text-encoder training; saves ~400 MB VRAM |
| **Token Control** | `--keep_tokens=1 --shuffle_caption` | Keeps `rexstyle` first while shuffling rest for style generalization |
| **Windows Stability** | `--caption_extension=.txt --save_model_as=safetensors --max_data_loader_n_workers=0 --seed=42` | Avoids DataLoader hangs and ensures safetensors output |
| **Network Rank** | `16` (`network_dim=16`) | Optimal style convergence |
| **Steps** | `1200` steps | Checkpoint saved every 250 steps |
| **OOM Fallback** | Auto-retry with `rank 8` & `448px` | Automatically recovers without silent model switching |

---

## 6. How to Run Training

### Dry-Run Verification (Outputs exact command without launching):
```powershell
python -m src.cli train-local --dry-run
```

### Start Full Training Run:
```powershell
python -m src.cli train-local --steps 1200 --rank 16
```

### What to Watch in the First 5 Minutes:
- **Good signs:** Progress bar advancing with steps, loss hovering between `0.05` and `0.15` (normal fluctuation).
- **Bad signs:**
  - *"CUDA out of memory"*: Auto-retry will downscale to rank 8 / 448px.
  - *Hang with zero progress*: Verify `--max_data_loader_n_workers=0`.
  - *bitsandbytes error*: Rerun with `--optimizer Adafactor`.
- **Expected Speed:** ~2 to 5 seconds per step on RTX 3050 Laptop (~1 to 2.5 hours total for 1,200 steps).

### Evaluating Checkpoints:
Training generates 5 checkpoint `.safetensors` files in `./models/` (at steps 250, 500, 750, 1000, 1200):
1. Test the same 3 prompts across checkpoints at scale `0.7`, `0.8`, and `1.0`:
   ```powershell
   python -m src.cli generate --topic "Resilient Distributed Systems" --backend local --lora models/rexstyle_lora-step00000500.safetensors
   ```
2. With 16 style reference photos, the **500 or 750 step checkpoint** is often the sweet spot (captures the bold vector aesthetic without overfitting or copying facial features).
3. Set your favorite checkpoint in `config/lora.json` as the default.

---

## 7. How to Generate Images with Your Local LoRA

Once trained, generate visuals with model CPU offloading (runs comfortably in ~2.5 GB VRAM):

```powershell
python -m src.cli generate --topic "Resilient Distributed Systems" --backend local --lora models/rexstyle_lora.safetensors
```
This generates at **512x640** (4:5 portrait) and exports crisp **1080x1350** images via `export.py` with code-rendered typography overlays.
