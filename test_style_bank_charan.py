"""Test script for building style_bank from 차란 data."""

from pathlib import Path
from tools.userchat_style_bank import build_style_bank, format_style_references_for_prompt
import json

# 차란 데이터 경로
CHARAN_DIR = Path("~/Desktop/ax-task/차란/01_clustering").expanduser()
MESSAGES_CSV = CHARAN_DIR / "차란_messages.csv"
TAGS_XLSX = CHARAN_DIR / "차란_tags.xlsx"

def main():
    print("=" * 80)
    print("차란 Style Bank 테스트")
    print("=" * 80)

    # Build style bank
    print("\n[1] Building style bank...")
    bank = build_style_bank(
        messages_csv=MESSAGES_CSV,
        cluster_tags_xlsx=TAGS_XLSX,
        top_k=5,
        min_length=10,
        max_length=200,
    )

    print(f"✅ Built style bank with {len(bank)} clusters\n")

    # Display sample clusters
    print("[2] Sample clusters:")
    print("-" * 80)

    for i, (cluster_id, data) in enumerate(bank.items()):
        if i >= 3:  # Show first 3 clusters only
            break

        print(f"\n📦 Cluster {cluster_id}: {data['label']}")
        print(f"   발화 개수: {len(data['utterances'])}")
        print("\n   실제 고객 발화:")
        for j, utt in enumerate(data['utterances'], 1):
            print(f"   {j}. \"{utt}\"")

    print("\n" + "-" * 80)

    # Test formatting for prompt
    print("\n[3] Formatted prompt section (for scenario generation):")
    print("-" * 80)

    # Pick first cluster
    first_cluster = next(iter(bank.values()))
    formatted = format_style_references_for_prompt(
        utterances=first_cluster['utterances'][:3],
        prefix="실제 고객 발화 예시"
    )
    print(formatted)
    print("-" * 80)

    # Save bank to JSON for inspection
    output_path = Path("~/qa-agent/storage/charan_style_bank.json").expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Style bank saved to: {output_path}")
    print(f"   Total clusters: {len(bank)}")
    print(f"   Total utterances: {sum(len(d['utterances']) for d in bank.values())}")

    # Statistics
    print("\n[4] Statistics:")
    print("-" * 80)
    utterance_counts = [len(d['utterances']) for d in bank.values()]
    print(f"   Average utterances per cluster: {sum(utterance_counts) / len(utterance_counts):.1f}")
    print(f"   Min utterances: {min(utterance_counts)}")
    print(f"   Max utterances: {max(utterance_counts)}")

if __name__ == "__main__":
    main()
