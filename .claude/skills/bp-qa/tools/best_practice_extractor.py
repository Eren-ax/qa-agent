"""Extract Best Practice cases from sop-agent clustering results.

Selects representative user chats from each cluster to ensure:
1. Coverage of all major intent categories
2. Distribution proportional to cluster sizes
3. Preference for high-quality conversations (CSAT, resolution time, etc.)

Usage:
    from tools.best_practice_extractor import extract_best_practices

    bp_cases = extract_best_practices(
        clustered_excel="~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx",
        target_total=100,
        filters={
            "min_cluster_size": 10,  # Ignore tiny clusters
            "require_alf": False,     # Include non-ALF chats
            "priority_tags": ["urgent", "high"],  # Prioritize these
        }
    )
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from tools.outcome_scorer import calculate_outcome_score
from tools.adoption_classifier import classify_task_type, TaskClassification


@dataclass
class BestPracticeCase:
    """One Best Practice user chat extracted from clustering."""

    user_chat_id: str
    user_chat_url: str
    cluster_id: int
    cluster_label: str
    cluster_category: str
    cluster_size: int

    # Customer message
    enhanced_text: str  # Full conversation text

    # Metadata for filtering/prioritization
    tags: list[str]
    priority: str  # high, medium, low
    state: str  # closed, opened, etc.
    csat: Optional[float]

    # Response info (for comparison)
    alf_triggered: bool
    time_to_first_answer: Optional[float]
    reply_count: int

    # Layer 1: Customer Satisfaction (Outcome)
    outcome_score: float = 0.0  # 0~7.0
    outcome_breakdown: Optional[dict] = None  # Detailed scores

    # Layer 3: Implementation Difficulty (Adoption)
    task_type: str = "Unknown"  # "RAG" | "Text Task" | "Function Task"
    task_type_confidence: float = 0.0  # 0.0~1.0
    task_type_reason: str = ""

    @property
    def intent(self) -> str:
        """Intent derived from cluster label."""
        return self.cluster_label

    @property
    def category_display(self) -> str:
        """Category for display."""
        return self.cluster_category or "기타"


def extract_best_practices(
    clustered_excel: str | Path,
    target_total: int = 100,
    filters: Optional[dict] = None,
    random_seed: int = 42,
    classify_adoption: bool = True,
) -> list[BestPracticeCase]:
    """Extract Best Practice cases from clustering results.

    Args:
        clustered_excel: Path to *_clustered.xlsx from sop-agent Stage 1
        target_total: Target number of cases to extract
        filters: Optional filters:
            - min_cluster_size: Minimum cluster size (default: 10)
            - require_alf: Only include ALF-triggered chats (default: False)
            - priority_tags: Tags to prioritize (default: [])
            - max_per_cluster: Max cases per cluster (default: 10)
        random_seed: Random seed for reproducibility
        classify_adoption: Classify task type (Layer 3) (default: True)

    Returns:
        List of BestPracticeCase, distributed across clusters
    """
    filters = filters or {}
    min_cluster_size = filters.get("min_cluster_size", 10)
    require_alf = filters.get("require_alf", False)
    priority_tags = filters.get("priority_tags", [])
    max_per_cluster = filters.get("max_per_cluster", 10)

    random.seed(random_seed)

    # Load clustering data
    excel_path = Path(clustered_excel).expanduser()
    if not excel_path.exists():
        raise FileNotFoundError(f"Clustering Excel not found: {excel_path}")

    df = pd.read_excel(excel_path)

    # Filter out rows without clustering
    df = df[df['cluster_id'].notna()].copy()

    # Filter by cluster size
    cluster_sizes = df.groupby('cluster_id').size()
    valid_clusters = cluster_sizes[cluster_sizes >= min_cluster_size].index
    df = df[df['cluster_id'].isin(valid_clusters)]

    if len(df) == 0:
        raise ValueError(f"No valid clusters found (min_cluster_size={min_cluster_size})")

    # Filter by ALF if required
    if require_alf:
        df = df[df['alfTriggered'] == True]

    # Calculate per-cluster allocation (proportional to size)
    cluster_counts = df['cluster_id'].value_counts()
    total_chats = cluster_counts.sum()

    allocation = {}
    for cluster_id, count in cluster_counts.items():
        # Proportional allocation
        target = int(target_total * count / total_chats)
        # Cap at max_per_cluster
        target = min(target, max_per_cluster)
        # Ensure at least 1 per cluster
        target = max(target, 1)
        allocation[cluster_id] = target

    # Adjust to hit target_total exactly
    current_total = sum(allocation.values())
    if current_total < target_total:
        # Add to largest clusters
        sorted_clusters = sorted(allocation.items(), key=lambda x: cluster_counts[x[0]], reverse=True)
        diff = target_total - current_total
        for i in range(diff):
            cluster_id = sorted_clusters[i % len(sorted_clusters)][0]
            if allocation[cluster_id] < max_per_cluster:
                allocation[cluster_id] += 1
    elif current_total > target_total:
        # Remove from smallest allocations
        sorted_clusters = sorted(allocation.items(), key=lambda x: x[1])
        diff = current_total - target_total
        for i in range(diff):
            cluster_id = sorted_clusters[i % len(sorted_clusters)][0]
            if allocation[cluster_id] > 1:
                allocation[cluster_id] -= 1

    # Sample from each cluster
    selected_cases = []

    for cluster_id, target_count in allocation.items():
        cluster_df = df[df['cluster_id'] == cluster_id].copy()

        # Calculate outcome score (Layer 1: Customer Satisfaction)
        outcome_results = cluster_df.apply(
            lambda row: calculate_outcome_score(row, all_data=df),
            axis=1
        )

        cluster_df['outcome_score'] = outcome_results.apply(lambda x: x['total'])
        cluster_df['outcome_breakdown'] = outcome_results.apply(lambda x: x['scores'])

        # Additional priority adjustments
        if priority_tags:
            has_priority = cluster_df['tags'].apply(
                lambda x: any(tag in str(x).lower() for tag in priority_tags) if pd.notna(x) else False
            )
            # Add bonus to outcome_score for priority cases
            cluster_df.loc[has_priority, 'outcome_score'] += 0.5

        # Sort by outcome score, then sample
        cluster_df = cluster_df.sort_values('outcome_score', ascending=False)

        # Take top N, with some randomness
        if len(cluster_df) <= target_count:
            sampled = cluster_df
        else:
            # Take top 50%, then randomly sample
            top_half = cluster_df.head(int(len(cluster_df) * 0.5))
            if len(top_half) <= target_count:
                sampled = top_half
            else:
                sampled = top_half.sample(n=target_count, random_state=random_seed + cluster_id)

        # Convert to BestPracticeCase
        for _, row in sampled.iterrows():
            # Classify task type (Layer 3)
            if classify_adoption:
                task_classification = classify_task_type(
                    intent=row['label'] if pd.notna(row['label']) else "",
                    enhanced_text=row['enhanced_text'] if pd.notna(row['enhanced_text']) else "",
                    alf_triggered=bool(row['alfTriggered']) if pd.notna(row['alfTriggered']) else False,
                    use_llm_fallback=False  # Use heuristic only for speed
                )
            else:
                task_classification = TaskClassification(
                    task_type="Unknown",
                    confidence=0.0,
                    reason="Classification skipped"
                )

            case = BestPracticeCase(
                user_chat_id=row['id'],
                user_chat_url=row['url'],
                cluster_id=int(row['cluster_id']),
                cluster_label=row['label'] if pd.notna(row['label']) else f"Cluster {row['cluster_id']}",
                cluster_category=row['category'] if pd.notna(row['category']) else "기타",
                cluster_size=int(cluster_counts[row['cluster_id']]),
                enhanced_text=row['enhanced_text'] if pd.notna(row['enhanced_text']) else "",
                tags=str(row['tags']).split(',') if pd.notna(row['tags']) else [],
                priority=row['priority'] if pd.notna(row['priority']) else "medium",
                state=row['state'] if pd.notna(row['state']) else "unknown",
                csat=float(row['profile.csat']) if pd.notna(row['profile.csat']) else None,
                alf_triggered=bool(row['alfTriggered']) if pd.notna(row['alfTriggered']) else False,
                time_to_first_answer=float(row['timeToFirstAnswer']) if pd.notna(row['timeToFirstAnswer']) else None,
                reply_count=int(row['replyCount']) if pd.notna(row['replyCount']) else 0,
                outcome_score=float(row['outcome_score']),
                outcome_breakdown=row['outcome_breakdown'],
                task_type=task_classification.task_type,
                task_type_confidence=task_classification.confidence,
                task_type_reason=task_classification.reason,
            )
            selected_cases.append(case)

    return selected_cases


def generate_bp_report(cases: list[BestPracticeCase], output_path: str | Path) -> None:
    """Generate a markdown report of selected Best Practice cases.

    Args:
        cases: List of BestPracticeCase
        output_path: Where to save the report
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by category
    by_category = {}
    for case in cases:
        cat = case.category_display
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(case)

    # Generate report
    lines = [
        "# Best Practice Cases - Selection Report",
        "",
        f"**Total cases:** {len(cases)}",
        f"**Categories:** {len(by_category)}",
        "",
        "## Distribution by Category",
        "",
        "| Category | Cases | % |",
        "|----------|-------|---|",
    ]

    for cat in sorted(by_category.keys()):
        cat_cases = by_category[cat]
        pct = len(cat_cases) / len(cases) * 100
        lines.append(f"| {cat} | {len(cat_cases)} | {pct:.1f}% |")

    lines.extend([
        "",
        "## Cases by Category",
        "",
    ])

    for cat in sorted(by_category.keys()):
        lines.extend([
            f"### {cat}",
            "",
        ])

        cat_cases = by_category[cat]
        for i, case in enumerate(cat_cases, 1):
            lines.extend([
                f"#### {i}. {case.intent}",
                "",
                f"- **User Chat ID:** {case.user_chat_id}",
                f"- **URL:** {case.user_chat_url}",
                f"- **Cluster:** {case.cluster_id} (size: {case.cluster_size})",
                f"- **Tags:** {', '.join(case.tags[:5])}",
                f"- **Priority:** {case.priority}",
                f"- **State:** {case.state}",
                f"- **CSAT:** {case.csat if case.csat else 'N/A'}",
                f"- **ALF Triggered:** {'Yes' if case.alf_triggered else 'No'}",
                "",
                "**Customer Message:**",
                "```",
                case.enhanced_text[:300] + "..." if len(case.enhanced_text) > 300 else case.enhanced_text,
                "```",
                "",
            ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Report saved to: {output_path}")


if __name__ == "__main__":
    # Test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python best_practice_extractor.py <clustered_excel> [target_total]")
        sys.exit(1)

    clustered_excel = sys.argv[1]
    target_total = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    cases = extract_best_practices(
        clustered_excel=clustered_excel,
        target_total=target_total,
    )

    print(f"\n✅ Extracted {len(cases)} Best Practice cases")
    print(f"\nDistribution:")
    from collections import Counter
    cat_counts = Counter(c.category_display for c in cases)
    for cat, count in cat_counts.most_common():
        print(f"  {cat}: {count}")

    # Generate report
    output_path = Path("storage/best_practice_selection.md")
    generate_bp_report(cases, output_path)
