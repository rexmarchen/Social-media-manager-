# linkedin-image-agent

An autonomous, production-grade visual generation pipeline for LinkedIn posts. Designed for **Anshu Pal / REXION**, it crafts high-engagement, tactile retro-futuristic visuals with precision typography and zero local GPU requirements.

---

## Architecture Overview (Phase 1)

```
[ Raw Dataset ] (16 images in ./dataset/raw/)
       │
       ▼  (python -m src.cli prep)
[ Clean Dataset ] (Standardized to 1024+ px, dHash deduplicated, RGB JPGs)
       │
       ▼  (python -m src.cli caption)
[ Paired .txt + .json ] (Dense vision captions prepended with `rexstyle`)
       │
       ▼  (python -m src.cli styleguide)
[ config/style_guide.md ] (Aesthetic DNA, palette rules, composition guidelines)
       │
       ▼  (python -m src.cli create-basic)
[ 1024x1280 Raw Generation ] ──► [ Quality Gate Check ] ──► [ Typography Engine ] ──► [ 1080x1350 Export ]
```

---

## LinkedIn Official API Specifications

### API Versioning Header
LinkedIn uses versioned REST APIs (monthly `YYYYMM` cadence with a 12-month lifecycle). Per current official LinkedIn Developer Documentation and project configuration:
```http
LinkedIn-Version: 202603
X-Restli-Protocol-Version: 2.0.0
```
*(Configurable via `LINKEDIN_VERSION` in `.env`)*

### Required OAuth 2.0 Scopes
| Scope | Description | Required? |
| :--- | :--- | :--- |
| `w_member_social` | Create, modify, and delete posts, comments, and reactions on member profile | **Yes (Mandatory)** |
| `openid` | OpenID Connect token for secure identity assertion | **Yes (Mandatory)** |
| `profile` | Retrieve user profile information and resolve member URN (`urn:li:person:...`) | **Yes (Mandatory)** |
| `email` | Retrieve user primary email address | **Yes** |
| `w_organization_social` | Publish posts to LinkedIn company/organization pages | Optional (Org only) |

---

## fal.ai API Specifications (Verified)

Before building Phase 2 LoRA fine-tuning, the parameter schemas for fal.ai were verified against official API documentation:

### 1. LoRA Training Endpoint: `fal-ai/flux-lora-fast-training`
* **`images_data_url`** (`string`, URL): Direct URL pointing to a zip file of image and `.txt` caption pairs. Uploaded using `fal_client.upload_file(zip_path)`.
* **`trigger_word`** (`string`): The activation word (`"rexstyle"`).
* **`is_style`** (`boolean`): Must be set to `True`. Setting `is_style: true` instructs the trainer that the dataset teaches visual aesthetics and layout rather than a single physical object or person, disabling automated subject segmentation.
* **`steps`** (`integer`, default `1000`): Recommended 1000 steps for FLUX.1 [dev] style adapters.
* **`learning_rate`** (`float`, default `0.0008`): Optimized default for style convergence.
* **Output**: Returns `result["diffusers_lora_file"]["url"]` containing the hosted `.safetensors` download URL.

### 2. LoRA Inference Endpoint: `fal-ai/flux-lora`
* **`prompt`** (`string`): Prompt starting with `rexstyle, ...`.
* **`image_size`** (`object`): `{"width": 1024, "height": 1280}` (exact 4:5 aspect ratio, multiples of 16).
* **`loras`** (`list[object]`): `[{"path": "<lora_safetensors_url>", "scale": 1.0}]`.
* **`num_images`** (`integer`): Number of candidates (default 1 to 3).
* **`num_inference_steps`** (`integer`, default `28`).
* **`guidance_scale`** (`float`, default `3.5`).
* **`output_format`** (`string`, default `"jpeg"`).
* **Output**: Returns `result["images"][i]["url"]`.

---

## Setup & Quickstart

### 1. Installation
```powershell
pip install -r requirements.txt
```

### 2. Environment Variables (.env)
Create `.env` based on `.env.example`:
```env
GEMINI_API_KEY=your_gemini_key      # or OPENAI_API_KEY / ANTHROPIC_API_KEY
FAL_KEY=your_fal_key                # Optional for Phase 1 test generation
LINKEDIN_ACCESS_TOKEN=your_token
LINKEDIN_PERSON_URN=urn:li:person:...
```

### 3. Run Phase 1 Step-by-Step

#### Step A: Prepare & Deduplicate Raw Dataset
Takes raw images in `./dataset/raw/`, eliminates near-duplicates using 64-bit dHash, scales long-edge to 1024px+, converts to RGB, and saves to `./dataset/clean/`:
```powershell
python -m src.cli prep
```

#### Step B: Generate Visual Captions & Metadata
Runs Vision LLM on all cleaned images to create dense descriptive captions prepended with `rexstyle`:
```powershell
python -m src.cli caption
```

#### Step C: Synthesize Brand Style Guide
Aggregates dataset metadata into a comprehensive markdown guide at `config/style_guide.md`:
```powershell
python -m src.cli styleguide
```

#### Step D: Train Flux LoRA Style Adapter on fal.ai (Phase 2)
Displays estimated cost (~$2.20 USD for 1,000 steps), asks for confirmation, packages `dataset/clean/`, uploads to fal storage, polls logs, saves `config/lora.json`, and downloads `.safetensors` to `./models/`:
```powershell
python -m src.cli train --steps 1000
```

#### Step E: Side-by-Side LoRA Evaluation (`compare`)
Generates 3 benchmark prompts with and without the trained LoRA, stitching them side-by-side into `outputs/comparisons/` for visual evaluation:
```powershell
python -m src.cli compare --scale 1.0
python -m src.cli compare --scale 0.8
```

#### Step F: Generate Image Candidates with Configurable LoRA Scale
Generates 1024x1280 (4:5) candidate visual frames using the trained LoRA (scale configurable between 0.0 and 1.5, default 1.0):
```powershell
python -m src.cli generate --topic "Microservices vs Modular Monoliths" --scale 1.0 --count 3
```

#### Step G: Inspect Visual Quality
Evaluates generated candidate using Vision LLM for artifact freedom, negative space, and brand tone:
```powershell
python -m src.cli check outputs/generated/<candidate_filename>.jpg
```

#### Step H: Apply Typography Engine Overlay
Overlays brand typography using `assets/fonts/heading.ttf` (Georgia) and `body.ttf` (Segoe UI):
```powershell
python -m src.cli overlay outputs/generated/<candidate_filename>.jpg --headline "Architecting Distributed Systems"
```

#### Step I: Export Standard Formats & Multi-Page PDF Carousel
Resizes 1024x1280 into 1080x1350 (4:5 Portrait), 1080x1080 (Square), and 1200x627 (Landscape), strictly maintaining <5MB file size:
```powershell
python -m src.cli export outputs/drafts/<overlay_filename>.jpg --name "system_design_post"
```
Or create a multi-page PDF carousel:
```powershell
python -m src.cli carousel slide1.jpg slide2.jpg slide3.jpg --output outputs/drafts/carousel.pdf
```

---

## Single All-in-One Command (`create-basic`)

To test the entire Phase 1 pipeline in a single step:
```powershell
python -m src.cli create-basic --topic "Autonomous Agent Architecture"
```
This automatically:
1. Constructs an on-brand Flux prompt with trigger word `rexstyle`.
2. Generates a 1024x1280 base frame.
3. Scores composition and detects safe negative space with Vision LLM.
4. Overlays heading display serif typography.
5. Exports the final 1080x1350 portrait image into `outputs/drafts/`.

---

## Running Unit Tests
```powershell
pytest
```
All unit tests validate image standardization, dHash deduplication, typography engine word-wrapping, and export resizing.
