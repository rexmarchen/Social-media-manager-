"""
Performance Evaluation Skill
----------------------------
Tracks and compares post performance metrics (impressions, reactions, comments, clicks),
providing strategic feedback to guide future topics and visual styles.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List
from .content_memory import ContentMemory

log = logging.getLogger("performance_eval")


class PerformanceEvaluator:
    def __init__(self, content_memory: ContentMemory | None = None):
        self.memory = content_memory or ContentMemory()

    def record_metrics(
        self,
        post_id: str,
        reactions: int = 0,
        comments: int = 0,
        reposts: int = 0,
        impressions: int = 0,
    ) -> bool:
        """Attaches performance metrics to an existing memory record."""
        for item in self.memory.records:
            if item.get("post_id") == post_id or item.get("linkedin_post_urn") == post_id:
                item["performance_metrics"] = {
                    "updated_at": datetime.now().isoformat(),
                    "reactions": reactions,
                    "comments": comments,
                    "reposts": reposts,
                    "impressions": impressions,
                    "engagement_rate": round((reactions + comments * 2) / max(1, impressions) * 100, 2),
                }
                self.memory._save()
                log.info("Saved performance metrics for post %s", post_id)
                return True
        return False

    def get_strategy_report(self) -> dict[str, Any]:
        """Analyzes top performing topics and styles from recorded history."""
        records = [r for r in self.memory.records if r.get("performance_metrics")]
        if not records:
            return {
                "total_tracked_posts": len(self.memory.records),
                "top_categories": ["Backend Engineering & Databases", "Distributed Systems & Performance"],
                "recommended_formats": ["1.91:1 High-contrast 3D isometric infographic"],
                "best_time_to_post": "19:30 IST (Mon, Wed, Fri)",
                "insights": "Continue emphasizing real engineering lessons and measured p95/p99 latency improvements."
            }

        # Sort by engagement
        sorted_records = sorted(
            records,
            key=lambda x: x["performance_metrics"].get("reactions", 0) + x["performance_metrics"].get("comments", 0) * 2,
            reverse=True,
        )

        top = sorted_records[:3]
        return {
            "total_tracked_posts": len(self.memory.records),
            "top_performing_topics": [t.get("topic") for t in top],
            "top_styles": [t.get("visual_brief", {}).get("style_category") for t in top],
            "insights": "Posts with visual architecture diagrams and specific debugging trade-offs generate higher comment volume."
        }
