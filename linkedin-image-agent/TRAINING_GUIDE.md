# Free SDXL LoRA Training Guide (Google Colab & Kaggle)

This guide walks you through training your custom **`rexstyle`** SDXL LoRA for **$0.00** using Google Colab or Kaggle with a free GPU.

---

## 1. Prerequisites
1. Run `python -m src.cli export-training-kit` in your workspace.
2. This generates:
   - `outputs/training_kit.zip` (containing your prepared images and text captions).
   - `notebooks/train_sdxl_lora_colab.ipynb` (the ready-to-run Jupyter notebook).

---

## 2. Option A: Google Colab (Recommended)

### Step 1: Open Google Colab
1. Go to [Google Colab](https://colab.research.google.com).
2. Click **File > Upload Notebook** and select `notebooks/train_sdxl_lora_colab.ipynb` from this project.

### Step 2: Enable Free T4 GPU
1. In the top menu, go to **Runtime > Change runtime type**.
2. Under **Hardware accelerator**, select **T4 GPU**.
3. Click **Save**.

### Step 3: Run the Notebook
1. Execute **Cell 1** to confirm GPU allocation (`Tesla T4`, ~15 GB VRAM).
2. Execute **Cell 2** to install dependencies (`kohya_ss sd-scripts`, `xformers`, `diffusers`, `accelerate`).
3. Execute **Cell 3**: when prompted, upload `outputs/training_kit.zip`.
4. Execute **Cell 4** to start the training run:
   - **Resolution**: `1024x1024`
   - **LoRA Rank (Dim)**: `16`
   - **Steps**: `1200` (~15 to 25 minutes runtime)
   - **Checkpoints**: Saved every 250 steps to `/content/output/`.
5. Execute **Cell 5** to test a sample generation using your newly trained LoRA.
6. Execute **Cell 6** to automatically download `rexstyle_sdxl_lora.safetensors` to your computer.

### Step 4: Import into linkedin-image-agent
Place the downloaded file into the `models/` directory:
```powershell
linkedin-image-agent/models/rexstyle_sdxl_lora.safetensors
```

---

## 3. Option B: Kaggle Notebooks
1. Go to [Kaggle](https://www.kaggle.com) and create a new Notebook.
2. In the right panel under **Settings**:
   - Turn **Internet** ON.
   - Set **Accelerator** to **GPU T4 x 2** or **GPU P100**.
3. Upload `training_kit.zip` as a dataset.
4. Paste the cells from `train_sdxl_lora_colab.ipynb` and run.
5. Download the output `.safetensors` file.

---

## 4. Using Your Trained LoRA Locally

To run generation using your downloaded LoRA:

```powershell
# With diffusers (requires a local NVIDIA GPU with CUDA):
python -m src.cli generate --topic "Resilient Distributed Systems" --local-lora models/rexstyle_sdxl_lora.safetensors

# Or via fal.ai inference (paid cloud fallback):
python -m src.cli generate --topic "Resilient Distributed Systems" --backend fal
```
