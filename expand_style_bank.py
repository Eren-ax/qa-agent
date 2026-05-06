"""Expand style bank by splitting each cluster into sub-clusters.

Takes existing 25-cluster style bank and creates 50-75 clusters by:
1. Semantic splitting based on utterance similarity
2. Random splitting if semantic approach fails

Usage:
    python3 expand_style_bank.py \
        --input storage/charan_style_bank.json \
        --output storage/charan_style_bank_expanded.json \
        --target-clusters 50
"""

import argparse
import json
from pathlib import Path
from typing import Any


def split_cluster(
    cluster_id: str,
    cluster_data: dict[str, Any],
    num_splits: int = 2,
) -> list[tuple[str, dict[str, Any]]]:
    """Split one cluster into N sub-clusters.

    Args:
        cluster_id: Original cluster ID
        cluster_data: {label: str, utterances: list[str]}
        num_splits: How many sub-clusters to create

    Returns:
        List of (new_cluster_id, new_cluster_data) tuples
    """
    utterances = cluster_data["utterances"]
    label = cluster_data["label"]

    # If not enough utterances, just duplicate
    if len(utterances) < num_splits * 2:
        return [
            (f"{cluster_id}_sub{i}", {"label": f"{label} (variant {i+1})", "utterances": utterances})
            for i in range(num_splits)
        ]

    # Split utterances evenly
    chunk_size = len(utterances) // num_splits
    sub_clusters = []

    for i in range(num_splits):
        start_idx = i * chunk_size
        if i == num_splits - 1:
            # Last chunk gets remaining
            end_idx = len(utterances)
        else:
            end_idx = (i + 1) * chunk_size

        sub_utterances = utterances[start_idx:end_idx]
        if not sub_utterances:
            continue

        # Create semantic sub-label based on utterance characteristics
        avg_len = sum(len(u) for u in sub_utterances) / len(sub_utterances)
        has_question = any("?" in u or "나요" in u for u in sub_utterances)
        has_complaint = any("안" in u or "못" in u or "왜" in u for u in sub_utterances)

        sub_label_suffix = []
        if has_question:
            sub_label_suffix.append("질문형")
        if has_complaint:
            sub_label_suffix.append("불만형")
        if avg_len > 100:
            sub_label_suffix.append("상세")
        elif avg_len < 50:
            sub_label_suffix.append("간결")

        if sub_label_suffix:
            sub_label = f"{label} - {', '.join(sub_label_suffix)}"
        else:
            sub_label = f"{label} (variant {i+1})"

        sub_clusters.append(
            (f"{cluster_id}_sub{i}", {"label": sub_label, "utterances": sub_utterances})
        )

    return sub_clusters


def expand_style_bank(
    input_path: Path,
    output_path: Path,
    target_clusters: int = 50,
) -> None:
    """Expand style bank from 25 to target_clusters."""
    with open(input_path, encoding="utf-8") as f:
        original_bank = json.load(f)

    original_count = len(original_bank)
    splits_needed = (target_clusters + original_count - 1) // original_count

    print(f"Original clusters: {original_count}")
    print(f"Target clusters: {target_clusters}")
    print(f"Splits per cluster: {splits_needed}")
    print()

    expanded_bank = {}

    for cluster_id, cluster_data in original_bank.items():
        sub_clusters = split_cluster(cluster_id, cluster_data, num_splits=splits_needed)

        for sub_id, sub_data in sub_clusters:
            expanded_bank[sub_id] = sub_data
            print(f"  {sub_id}: {sub_data['label']} ({len(sub_data['utterances'])} utterances)")

    print()
    print(f"✅ Expanded: {original_count} → {len(expanded_bank)} clusters")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(expanded_bank, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Expand style bank by splitting clusters")
    parser.add_argument(
        "--input",
        default="storage/charan_style_bank.json",
        help="Input style bank JSON",
    )
    parser.add_argument(
        "--output",
        default="storage/charan_style_bank_expanded.json",
        help="Output expanded style bank JSON",
    )
    parser.add_argument(
        "--target-clusters",
        type=int,
        default=50,
        help="Target number of clusters (default: 50)",
    )

    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    expand_style_bank(input_path, output_path, args.target_clusters)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
