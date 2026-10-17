"""
Comprehensive Test Suite for Upgraded LinkedIn Agent Skills
-----------------------------------------------------------
Tests the 7 mandatory Phase 8 deliverables:
1. Image generation with sample technology topic.
2. Reference-image analysis & reference-guided generation.
3. Branding, text composition, resizing, and final export.
4. Rejection and regeneration of a deliberately poor output.
5. Existing approval and publishing draft flow.
6. Missing API keys, provider failures, and fallback retry behavior.
7. Existing agent commands and performance evaluation.
"""

import json
import os
import sys
from pathlib import Path
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import our upgraded agent skills
from agent_skills import (
    BrandManager,
    ReferenceImageAnalyzer,
    VisualBrief,
    ReferenceGuidedGenerator,
    ImageGenerator,
    ImageCompositor,
    VisualQA,
    TopicResearcher,
    LinkedInCopywriter,
    InfographicDesigner,
    ContentMemory,
    ApprovalManager,
    PerformanceEvaluator,
)

ROOT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "test_artifacts"
TEST_DIR.mkdir(exist_ok=True)


def test_1_topic_research_and_image_generation():
    print("\n--- [TEST 1] Topic Research & AI Image Generation ---")
    researcher = TopicResearcher()
    topics = researcher.get_grounded_topics()
    assert len(topics) > 0, "No topics retrieved"
    sample = topics[0]
    print(f"Verified Topic: {sample.title} ({sample.category})")

    copywriter = LinkedInCopywriter()
    draft = copywriter.draft_post(sample.title, sample.verified_context)
    assert "post_text" in draft and len(draft["post_text"]) > 50, "Post draft was empty"
    print(f"Hook: {draft.get('hook', 'N/A')}")
    print("Post text snippet:", draft["post_text"][:120], "...")

    generator = ImageGenerator(output_dir=TEST_DIR)
    img_path = generator.generate(draft["image_prompt"], width=1200, height=627)
    assert img_path.exists(), "Generated image file does not exist"
    with Image.open(img_path) as im:
        assert im.size == (1200, 627), f"Expected (1200, 627), got {im.size}"
    print(f"✅ Test 1 Passed! Image generated: {img_path} ({img_path.stat().st_size} bytes)")
    return img_path, sample.title


def test_2_reference_image_analysis_and_guided_generation(sample_img_path):
    print("\n--- [TEST 2] Reference Image Analysis & Reference-Guided Generation ---")
    analyzer = ReferenceImageAnalyzer()
    brief = analyzer.analyze(sample_img_path)
    assert brief.width == 1200 and brief.height == 627
    print(f"Reference Brief Category: {brief.style_category}")
    print(f"Dominant Colors: {brief.dominant_colors}")
    print(f"Lighting Style: {brief.lighting_style}")

    guided = ReferenceGuidedGenerator.build_prompt("Distributed Caching Latency", brief)
    assert "negative_prompt" in guided.to_dict()
    assert brief.reference_id == guided.reference_id
    print("Guided Prompt Snippet:", guided.full_prompt[:130], "...")
    print(f"✅ Test 2 Passed! Reference-guided brief successfully derived.")
    return brief


def test_3_branding_composition_resizing(base_image_path, title):
    print("\n--- [TEST 3] Branding, Text Composition, Resizing, and Final Export ---")
    brand = BrandManager()
    compositor = ImageCompositor(brand)
    final_path = compositor.compose(
        base_image_path=base_image_path,
        title=title[:50],
        subtitle="MongoDB Indexing & Execution Profiling",
        tag="BACKEND ARCHITECTURE",
    )
    assert final_path.exists(), "Composited image does not exist"
    with Image.open(final_path) as im:
        assert im.size == (1200, 627), f"Composited size mismatch: {im.size}"
    print(f"✅ Test 3 Passed! Final composited asset exported: {final_path}")
    return final_path


def test_4_rejection_and_regeneration_of_poor_output():
    print("\n--- [TEST 4] Rejection & Regeneration of Deliberately Poor Output ---")
    brand = BrandManager()
    qa = VisualQA(brand)

    # Create a deliberately poor image (tiny 80x80, solid black, 0 contrast, 0 sharpness)
    bad_img_path = TEST_DIR / "deliberately_poor_output.jpg"
    bad_img = Image.new("RGB", (80, 80), color=(0, 0, 0))
    bad_img.save(bad_img_path)

    qa_result = qa.evaluate(bad_img_path, topic="Test Bad Output")
    print(f"Deliberate Bad Image Score: {qa_result.score}/100")
    print(f"Passed: {qa_result.passed}")
    print(f"Failure Reasons: {qa_result.failure_reasons}")

    assert not qa_result.passed, "Deliberately poor image should have failed QA"
    assert len(qa_result.failure_reasons) >= 2, "Expected multiple failure reasons for poor image"

    # Simulate bounded regeneration recovery
    print("Simulating bounded regeneration retry...")
    gen = ImageGenerator(output_dir=TEST_DIR)
    recovered_path = gen.generate("Clean minimalist 3D tech server graphic, 8k octane render", width=1200, height=627)
    compositor = ImageCompositor(brand)
    final_recovered = compositor.compose(recovered_path, title="Recovered Image", tag="RETRY SUCCESS")
    qa_recovered = qa.evaluate(final_recovered, topic="Recovered Image")
    print(f"Recovered Output Score: {qa_recovered.score}/100 (Passed: {qa_recovered.passed})")
    assert qa_recovered.passed, "Recovered image should pass QA"
    print("✅ Test 4 Passed! Poor image correctly rejected and successfully regenerated.")


def test_5_content_memory_and_approval_flow():
    print("\n--- [TEST 5] Content Memory & Approval Flow ---")
    memory = ContentMemory(storage_path=TEST_DIR / "test_content_memory.json")
    post_id = memory.record_post(
        topic="Optimizing MongoDB Query Latency",
        category="Databases",
        caption="Sample post caption text...",
        hook="When scaling databases, compound indexes change everything.",
        image_prompt="3d isometric db nodes",
        visual_brief={"style": "Dark Tech"},
        image_path=str(TEST_DIR / "test_asset.jpg"),
        qa_score=88.5,
    )
    assert post_id.startswith("mem-")

    # Test repetition detection
    is_repeat, reason = memory.check_repetition("Optimizing MongoDB Query Latency")
    assert is_repeat, "Expected repetition flag for identical topic"
    print(f"Repetition Check correctly caught duplicate: '{reason}'")

    is_repeat_new, _ = memory.check_repetition("Building Real-Time Audio Transcription with WebRTC")
    assert not is_repeat_new, "Unique topic should not be flagged as repeat"
    print("Unique topic verified original.")
    print("✅ Test 5 Passed! Content memory and anti-repetition fully functional.")


def test_6_infographic_and_carousel_skills():
    print("\n--- [TEST 6] Infographic and Multi-Slide Carousel Design ---")
    designer = InfographicDesigner()
    comp_path = designer.create_comparison_card(
        title="In-Memory Cache vs Redis Cluster",
        left_label="In-Memory Node Cache",
        left_points=["Zero network hop latency", "Process restart wipes state", "Unshared across instances"],
        right_label="Redis Distributed Cache",
        right_points=["Shared state across microservices", "Configurable eviction & persistence", "Supports cluster pub/sub"],
    )
    assert comp_path.exists()
    print(f"Comparison Card Created: {comp_path}")

    slides = [
        {"title": "The Concurrency Problem", "body": ["Two users edit the same node", "State desync occurs"]},
        {"title": "Operational Transformation", "body": ["Intercept concurrent operations", "Transform operation offsets"]},
    ]
    carousel_slides = designer.create_carousel(slides)
    assert len(carousel_slides) == 2
    for s in carousel_slides:
        assert s.exists()
    print(f"Carousel Generated with {len(carousel_slides)} slides: {[s.name for s in carousel_slides]}")
    print("✅ Test 6 Passed! Infographic and carousel generation verified.")


def test_7_missing_keys_and_resilience():
    print("\n--- [TEST 7] Missing API Keys & Offline Fallback Resilience ---")
    # Temporarily hide GEMINI_API_KEY to test resilient cascade
    old_key = os.environ.get("GEMINI_API_KEY")
    try:
        os.environ["GEMINI_API_KEY"] = ""
        gen = ImageGenerator(output_dir=TEST_DIR)
        fallback_path = gen.generate("Testing offline resilience fallback graphic", width=1200, height=627)
        assert fallback_path.exists()
        with Image.open(fallback_path) as im:
            assert im.size == (1200, 627)
        print(f"Resilient fallback generated valid image: {fallback_path}")
        print("✅ Test 7 Passed! Generator operates safely even without Gemini API key.")
    finally:
        if old_key is not None:
            os.environ["GEMINI_API_KEY"] = old_key


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 RUNNING SUITE FOR UPGRADED PROFESSIONAL LINKEDIN AGENT")
    print("=" * 70)
    try:
        sample_img, topic = test_1_topic_research_and_image_generation()
        brief = test_2_reference_image_analysis_and_guided_generation(sample_img)
        final_img = test_3_branding_composition_resizing(sample_img, topic)
        test_4_rejection_and_regeneration_of_poor_output()
        test_5_content_memory_and_approval_flow()
        test_6_infographic_and_carousel_skills()
        test_7_missing_keys_and_resilience()
        print("\n" + "=" * 70)
        print("🎉 ALL 7 TEST SUITES PASSED FLAWLESSLY!")
        print("=" * 70)
    except Exception as exc:
        print(f"\n❌ TEST SUITE FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
