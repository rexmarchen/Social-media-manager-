"""
Reference-Guided Generation Skill
---------------------------------
Translates visual briefs into synthesis prompts, separating style from subject,
ensuring brand and copyright safety (avoiding logo copying), and attaching metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any
from .reference_analysis import VisualBrief

log = logging.getLogger("reference_generation")


@dataclass
class GuidedPrompt:
    full_prompt: str
    style_guidance: str
    subject_guidance: str
    negative_prompt: str
    reference_id: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReferenceGuidedGenerator:
    @staticmethod
    def build_prompt(
        topic: str,
        visual_brief: VisualBrief,
        custom_subject: str | None = None,
    ) -> GuidedPrompt:
        """
        Synthesizes a new visual concept that borrows stylistic properties
        (lighting, palette, composition) without duplicating third-party trademarks or text.
        """
        # 1. Subject extraction
        clean_topic = topic.replace("Optimizing", "").replace("Building", "").strip()
        subject = custom_subject or f"Technical architecture visualization representing {clean_topic}"

        # 2. Style guidance derived from brief
        colors_str = ", ".join(visual_brief.dominant_colors[:3])
        style = (
            f"{visual_brief.style_category}, palette anchored in [{colors_str}], "
            f"{visual_brief.lighting_style}, {visual_brief.composition}"
        )

        # 3. Negative prompt to guard copyright and cleanliness
        negative = (
            "blurry, low resolution, noisy, watermark, brand logos, messy unreadable text, "
            "deformed geometry, cartoonish, low-poly, generic stock photo"
        )

        # 4. Assembled prompt
        full = (
            f"High-end 3D isometric technical render: {subject}. "
            f"Aesthetic: {style}. "
            f"Ultra-detailed octane render, 8k resolution, cinematic ambient occlusion, "
            f"minimalist dark tech composition, negative space for clean framing"
        )

        metadata = {
            "reference_id": visual_brief.reference_id,
            "style_category": visual_brief.style_category,
            "dominant_colors": visual_brief.dominant_colors,
            "preserve_subject": visual_brief.preserve_subject,
        }

        log.info("Constructed reference-guided prompt for topic: '%s'", topic)
        return GuidedPrompt(
            full_prompt=full,
            style_guidance=style,
            subject_guidance=subject,
            negative_prompt=negative,
            reference_id=visual_brief.reference_id,
            metadata=metadata,
        )

    @staticmethod
    def build_prompt_from_preset(
        topic: str,
        preset_name: str = "warm_editorial",
        custom_subject: str | None = None,
    ) -> GuidedPrompt:
        """
        Builds a dedicated prompt matching one of the trained aesthetic style families:
        1. 'warm_editorial' (REXION Signature workspace, warm cream, soft sunlight shadows, serif typography)
        2. 'halftone_wireframe' (Monochrome matte black, halftone dot matrix, 3D wireframe mesh)
        3. 'retro_tech' (Risograph paper grain, vintage CRT computer, pixelated serif typography)
        4. 'minimal_plain' (Solid dark matte charcoal, flat Swiss wireframe lines)
        """
        clean_topic = topic.replace("Optimizing", "").replace("Building", "").strip()
        subject = custom_subject or clean_topic

        negative = (
            "blurry, low quality, noisy, ugly, distorted text, oversaturated neon gradients, "
            "cheesy 3d cartoon, generic corporate stock photo, watermark"
        )

        if preset_name in ["warm_editorial", "warm", "editorial", "rexion"]:
            full = (
                f"Editorial graphic design poster for REXION showcasing {subject}. "
                "Warm neutral beige and cream background (#F6F2EC), soft natural morning daylight casting gentle dappled olive tree shadows from a window across a pristine wall. "
                "Sophisticated split composition: on the right, a minimalist light oak wooden desk with a sleek slim modern laptop, a speckled ceramic artisan coffee mug, a textured notebook and brass pen. "
                "On the left, clean open space with elegant high-contrast editorial serif typography ('REXION' logo at top left, 'BUILD / AUTOMATE / GROW' navigation), clean bullet points with circular icon badges, and a dark espresso brown pill button. "
                "Kinfolk and Japandi workspace aesthetic, architectural digest photography, calm, premium, ultra-high resolution 8k"
            )
            style_label = "Warm Editorial Workspace (REXION Signature)"
        elif preset_name in ["halftone_wireframe", "halftone", "wireframe", "cyber"]:
            full = (
                f"High-contrast monochrome technical graphic design poster exploring {subject}. "
                "Deep matte black background (#0A0A0A) with razor-sharp white and light gray linework. "
                "Featuring two elements interacting, one rendered in vintage halftone bitmap dot screenprint texture, and the other in an intricate 3D wireframe polygon vector grid mesh. "
                "Minimalist technical telemetry overlays, delicate coordinate measurement lines, orbital geometric reticles, and a single subtle warm peach indicator dot (#F5A623). "
                "Swiss typography, avant-garde design, retro-futuristic cryptography blueprint, crisp vector clarity, 8k resolution"
            )
            style_label = "Monochrome Halftone & 3D Wireframe"
        elif preset_name in ["retro_tech", "retro", "pixel"]:
            full = (
                f"Vintage retro-computing design poster about {subject}. "
                "Rich muted slate blue (#3B5F7F) or forest green canvas with subtle authentic Risograph paper texture. "
                "Featuring beautifully illustrated retro 1980s-1990s beige CRT desktop computers, CRT monitors, and vintage portable terminals with subtle screen scanlines. "
                "Playful yet sophisticated pixelated bitmap typography alongside crisp modern subtitles, minimalist pixel art icons (globe, sunburst, soundwave). "
                "Editorial poster aesthetic, nostalgic cyber culture, high resolution"
            )
            style_label = "Vintage Retro-Computing & Risograph"
        elif preset_name in ["cobalt_os", "cobalt", "os_blue"]:
            full = (
                f"Graphic design technical poster about {subject}. "
                "Bold monochromatic cobalt blue background (#1A36E8) with crisp stark white and light ice blue accents. "
                "Featuring a vintage desktop computer CRT monitor displaying glowing command lines, alongside an intricate 3D wireframe geometric wire sphere. "
                "Prominent bold condensed grotesque title, technical system explanation sidebar with line dividers, and high-contrast modernist layout. "
                "Avant-garde Swiss design, cybernetic hardware aesthetic, 8k resolution"
            )
            style_label = "Cobalt Blue OS & Retro Terminal"
        elif preset_name in ["mustard_retro", "mustard", "yellow_retro"]:
            full = (
                f"Minimalist retro-computing poster about {subject}. "
                "Deep warm mustard yellow background (#E5A922) with spacious negative space. "
                "In the center, a solitary vintage 1990s beige personal computer with mechanical keyboard and CRT monitor casting a soft realistic shadow. "
                "High-contrast black editorial serif typography with thoughtful reflective quote, clean modern layout, no clutter. "
                "Curated vintage hardware photography, gallery poster aesthetic, ultra-clean, 8k"
            )
            style_label = "Mustard Yellow Retro-Computing Poster"
        elif preset_name in ["macro_hardware", "hardware", "cpu_macro"]:
            full = (
                f"Editorial macro photograph and poster about {subject}. "
                "Soft textured slate denim blue backdrop (#4B6B8A). "
                "Hero close-up macro photograph of a ceramic microprocessor CPU chip with pristine gold-plated contact pins and silicon die reflecting soft studio light. "
                "Topped with elegant white editorial serif typography ('Trust the Processor' style), delicate architectural micro-subtitles. "
                "Stunning hardware engineering beauty, industrial design showcase, high resolution"
            )
            style_label = "Powder Blue Processor Macro"
        elif preset_name in ["tactile_notebook", "study_notebook", "desk_notebook"]:
            full = (
                f"Cozy tactile desk composition about {subject}. "
                "Close-up flatlay of a textured spiral-bound notebook and educational guide on a warm desk, clipped with a silver paper clip and a red A+ rubber stamp. "
                "Background of colorful curated bookstore bookshelf with vintage book spines softly out of focus. "
                "Clean editorial layout, tactile paper textures, inviting learning aesthetic, natural warm lighting"
            )
            style_label = "Tactile Desk & Study Notebook"
        else:
            full = (
                f"Minimalist flat design aesthetic tech graphic representing {subject}. "
                "Solid dark matte charcoal background (#121417) without gradients, crisp monochrome lines, minimal geometric architecture diagram representing distributed systems, "
                "Swiss typography layout, clean white and subtle muted gray accents, Dieter Rams and Linear design aesthetic, professional clean matte finish, 8k resolution"
            )
            style_label = "Swiss Minimalist Flat Wireframe"

        log.info("Constructed preset-guided prompt for '%s' using style '%s'", topic, style_label)
        return GuidedPrompt(
            full_prompt=full,
            style_guidance=style_label,
            subject_guidance=subject,
            negative_prompt=negative,
            reference_id=f"preset:{preset_name}",
            metadata={"preset": preset_name, "style_label": style_label},
        )
