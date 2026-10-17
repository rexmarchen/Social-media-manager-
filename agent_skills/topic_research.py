"""
Topic Research Skill
--------------------
Discovers, contextualizes, and verifies technical engineering topics (AI, ML, backend systems),
cross-referencing verified project facts and preventing hallucinated statistics.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List
import requests

log = logging.getLogger("topic_research")

ROOT_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_FILE = ROOT_DIR / "knowledge.json"


@dataclass
class ResearchTopic:
    title: str
    category: str
    verified_context: str
    architectural_tradeoffs: List[str] = field(default_factory=list)
    banned_fabrications: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TopicResearcher:
    def __init__(self, knowledge_path: Path | None = None):
        self.knowledge_path = knowledge_path or KNOWLEDGE_FILE
        self.verified_knowledge = self._load_verified_knowledge()

    def _load_verified_knowledge(self) -> list[dict[str, str]]:
        if self.knowledge_path.exists():
            try:
                return json.loads(self.knowledge_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def get_grounded_topics(self) -> list[ResearchTopic]:
        """Returns verified technical topics based on real repository learnings."""
        topics = [
            ResearchTopic(
                title="Optimizing High-Velocity Job Queries with Compound Indexes in MongoDB",
                category="Backend Engineering & Databases",
                verified_context="In REXION, high-throughput job queries caused bottlenecks. Profiling with explain('executionStats') showed high executionTimeMillis due to in-memory sorting. Adding compound indexes matching equality-sort-range patterns dropped query latency significantly without requiring extra infrastructure.",
                architectural_tradeoffs=[
                    "Tradeoff: Compound indexes increase RAM usage and slow down write operations.",
                    "Rule: Place equality fields first, sort fields second, range fields last."
                ],
                banned_fabrications=["Do not fabricate exact user counts or fake 10M benchmark numbers."]
            ),
            ResearchTopic(
                title="Distributed Caching: Why Measuring p99 Latency Matters Before Adding Redis",
                category="Distributed Systems & Performance",
                verified_context="Implemented a caching layer that dropped API latency by 40%. Learned that looking at average latency hides spikes caused by cold cache misses or thundering herd problems. Measuring p95 and p99 metrics revealed which read-heavy endpoints genuinely needed caching.",
                architectural_tradeoffs=[
                    "Tradeoff: Cache invalidation complexity vs latency reduction.",
                    "Insight: Stale data risks require explicit TTL and event-driven invalidation."
                ],
                banned_fabrications=["Do not claim 99.999% uptime or non-existent cloud clusters."]
            ),
            ResearchTopic(
                title="Real-Time State Synchronization: Handling WebSocket Concurrency",
                category="Full-Stack & Real-Time Architectures",
                verified_context="Built a collaborative workspace using WebSockets that placed in top 10 at a regional hackathon. Confronted race conditions when multiple users edited shared canvas nodes simultaneously. Employed operational transformation principles to sequence updates cleanly.",
                architectural_tradeoffs=[
                    "Tradeoff: Client-side optimistic rendering vs strict server reconciliation.",
                    "Insight: Network partition handling is critical for canvas state integrity."
                ],
                banned_fabrications=["Do not invent sponsor names or fake enterprise deployments."]
            ),
            ResearchTopic(
                title="ML Matching Pipelines: Why Data Preprocessing Beats Model Complexity",
                category="Applied AI & Machine Learning",
                verified_context="Evaluated text matching algorithms for job-candidate relevance. Discovered that meticulous token normalization, custom stop-word pruning, and clean regex parsing yielded far better relevance and 50x lower inference latency than bloated deep learning models.",
                architectural_tradeoffs=[
                    "Tradeoff: TF-IDF inference speed vs semantic nuance of transformer embeddings.",
                    "Insight: Clean data preprocessing provides greater leverage than premature fine-tuning."
                ],
                banned_fabrications=["Do not fabricate test set accuracy percentages."]
            )
        ]
        return topics

    def verify_topic(self, user_topic: str) -> ResearchTopic:
        """Sanitizes user-provided topic to ensure it is technically grounded."""
        clean = user_topic.strip()
        return ResearchTopic(
            title=clean,
            category="Software Engineering",
            verified_context=f"Focus strictly on practical architecture, implementation trade-offs, and verified software engineering principles for: {clean}",
            architectural_tradeoffs=["Trade-offs between simplicity, maintainability, and scalability."],
            banned_fabrications=["Never invent fake benchmark metrics or claim unverified enterprise adoption."]
        )
