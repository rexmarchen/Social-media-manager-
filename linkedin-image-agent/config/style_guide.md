# REXION Visual Style Guide (Trigger: `rexstyle`)

## 1. Core Aesthetic Philosophy
The REXION aesthetic (`rexstyle`) is a deliberate, high-end intersection of retro-computing nostalgia, tactile engineering, editorial minimalism, and technical architecture. It channels the spirit of 1990s desktop computing, vintage workstations, and industrial design, merged with modern AI-era digital curation. The visual language treats technology not as cold, sterile abstraction, but as a physical, craft-driven discipline—combining CRT glow, matte plastics, brushed metals, and gridded paper elements with sophisticated typographic hierarchy.

## 2. Dominant Color Palette & Color Usage Rules
The palette relies on high-contrast technical backdrops offset by vibrant primary utility colors and warm neutral foundations.

| Role | Color Name | HEX Code (Approx.) | Usage Percentage |
| :--- | :--- | :--- | :--- |
| **Primary Base** | Cobalt / Electric Blue | `#0F1E54` / `#2563EB` | 35% (Background gradients, structural UI) |
| **Primary Base** | Charcoal / Deep Black | `#09090B` / `#18181B` | 20% (Technical framing, deep shadows) |
| **Secondary Neutral** | Off-White / Cardstock | `#F3F4F6` / `#E5E7EB` | 20% (Matte paper surfaces, negative space) |
| **Secondary Neutral** | Brushed Silver / Slate | `#94A3B8` / `#64748B` | 10% (Metallic hardware, bezels, circuitry) |
| **Accent Utility** | Coral Pink / Orange | `#FF5722` / `#F43F5E` | 10% (Fuses, warning highlights, focal points) |
| **Accent Utility** | Emissive Cyan / Purple | `#06B6D4` / `#8B5CF6` | 5% (CRT phosphor glow, UI node highlights) |

*Usage Rules:*
- Maintain a minimum of 60% neutral/dark void or clean paper ground per composition.
- Use electric blues and cobalt as the foundational atmospheric wash.
- Restrict warm accents (coral/orange) to single focal points (e.g., a lit fuse, warning badge, or key UI element) to preserve editorial impact.

## 3. Signature Physical Props, Subjects & Textures
* **Vintage Computing Hardware:** 1990s desktop CRT monitors, beige mechanical keyboards, wired computer mice, desktop towers, floppy disks, and circuit boards.
* **Robotics & AI Mascots:** Friendly white-and-black modular robots, glossy plastic robot chassis, mechanical joints, glowing blue/cyan LED face screens and visor interfaces.
* **Tactile Stationery & Paper Goods:** Gridded green cutting mats, crumpled paper textures, newsprint, manila file folders, spiral notebooks, metal binder clips, paperclips, and sticky notes.
* **Curated Objects & Statuary:** Classical philosopher busts, ceramic mugs, chess pieces (knights, rooks), scattered charts, floating wireframe spheres, and abstract 3D geometric blocks.
* **Surface Finishes:** Matte plastic computer casings, brushed aluminum/steel laptops, glowing digital glass, glossy display foils, and textured cardstock.

## 4. Composition, Layout & Negative Space Rules
* **Aspect Ratio:** Optimized primarily for 4:5 vertical editorial formats (advertising posters, magazine covers, mobile feeds).
* **Grid & Alignment:** Strictly structured around asymmetrical editorial layouts, stark typographic zones, and technical diagrammatic framing.
* **Negative Space Allocation:** 
  - Reserve the upper third (top-half or upper quadrants) for clean headline typography, branding badges, or minimalist title headers.
  - Maintain generous breathing room along side margins or solid color blocks to prevent visual clutter.
* **Layering:** Combine 3D hardware elements with flat vector UI overlays, sticker motifs, and halftone print textures to create a mixed-media collage effect.

## 5. Lighting, Camera Angles & Depth of Field
* **Lighting Modes:** Clean, high-key studio diffusion combined with dramatic directional rim lighting. Features signature self-illuminating cyan/magenta CRT phosphor glows and warm edge highlights on metallic joints. Avoid flat, lifeless lighting; shadows must be soft, directional, and grounded.
* **Camera Angles:** Predominantly clean top-down flat-lays, 45-degree isometric studio perspectives, and dead-center editorial portraits.
* **Depth of Field:** Controlled shallow-to-medium depth of field. Foreground props and central hardware maintain razor-sharp tactile clarity, while background gradients or secondary collage layers fall into soft atmospheric falloff.

## 6. Prohibited Visual Tropes (The "Never Use" List)
* **Never Use:** Cheesy 3D fantasy avatars or generic corporate stock art people.
* **Never Use:** Neon rainbow gradients or overly saturated cyberpunk color explosions that lack industrial restraint.
* **Never Use:** Garbled, unreadable AI-generated text or faux-futuristic alien glyphs (typography must appear intentional, Swiss/editorial, or clean sans-serif layout).
* **Never Use:** Glossy, overly realistic human skin close-ups that break the stylized graphic/industrial illusion.
* **Never Use:** Chaotic, unanchored floating objects without gravitational logic or editorial framing.

## 7. Master Flux Prompt Formula & Golden Template
Use the following strict syntax template when generating images with the `rexstyle` LoRA:

> **Master Formula:**
> `rexstyle, [Subject/Core Object, e.g., a vintage CRT desktop computer and a friendly white robot mascot], set against a [Background style, e.g., cobalt blue gradient void with a green gridded cutting mat], [Materials, e.g., matte beige plastic, brushed aluminum, glowing digital cyan screen], [Lighting, e.g., soft diffused studio lighting with dramatic cyan rim glow and crisp contact shadows], [Composition, e.g., 4:5 vertical editorial poster composition, generous negative space in the upper quadrant for typography, mixed-media collage aesthetic], high-end tech advertising design, tactile clarity, 8k resolution.`

> **Golden Template Example:**
> `rexstyle, a vintage 1990s desktop computer monitor displaying an abstract UI wireframe alongside scattered paper notes and a mechanical keyboard, cobalt blue and off-white color palette, matte plastic and textured cardstock materials, top-down editorial flat-lay perspective, soft studio lighting with clean drop shadows, generous negative space at the top, minimal tech editorial poster design, high tactile realism.`
