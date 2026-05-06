"""Test Layer 2 (Utterance Transplant) scenario generation.

Generates 10 scenarios using real customer utterances from style_bank.
"""

from pathlib import Path
import json
import random

# Load style bank
STYLE_BANK_PATH = Path("~/qa-agent/storage/charan_style_bank.json").expanduser()

with open(STYLE_BANK_PATH, encoding="utf-8") as f:
    STYLE_BANK = json.load(f)

# Select diverse clusters for testing
def select_diverse_clusters(bank: dict, n: int = 10) -> list[tuple[str, dict]]:
    """Select diverse clusters for scenario generation."""
    clusters = list(bank.items())

    # Prioritize clusters with more utterances and diverse labels
    if len(clusters) <= n:
        return clusters

    # Random sample for diversity
    return random.sample(clusters, n)


def generate_layer2_scenario(
    cluster_id: str,
    cluster_data: dict,
    scenario_id: str,
    difficulty: str = "happy"
) -> dict:
    """Generate a scenario using Layer 2 (Utterance Transplant).

    Args:
        cluster_id: Cluster ID
        cluster_data: Cluster data with label and utterances
        scenario_id: Scenario ID
        difficulty: Difficulty tier (happy/edge/unhappy)

    Returns:
        Scenario dict
    """
    intent_label = cluster_data["label"]
    utterances = cluster_data["utterances"]

    # Select utterance based on difficulty
    if difficulty == "happy":
        # Pick shortest, most direct utterance
        selected = min(utterances, key=len)
    elif difficulty == "edge":
        # Pick medium-length with complexity
        sorted_by_len = sorted(utterances, key=len)
        selected = sorted_by_len[len(sorted_by_len) // 2]
    else:  # unhappy
        # Pick longest, most detailed (often contains complaints)
        selected = max(utterances, key=len)

    scenario = {
        "id": scenario_id,
        "intent": intent_label,
        "persona_ref": "polite_clear",  # Doesn't matter - we use real utterance
        "initial_message": selected,
        "difficulty_tier": difficulty,
        "source": "layer2-transplant",
        "source_cluster_id": cluster_id,
        "max_turns": 6,
        "metadata": {
            "utterance_length": len(selected),
            "is_real_customer": True,
            "generation_method": "utterance_transplant"
        }
    }

    return scenario


def main():
    print("=" * 80)
    print("Layer 2 (Utterance Transplant) 시나리오 생성 테스트")
    print("=" * 80)
    print(f"\nStyle Bank: {len(STYLE_BANK)} clusters, "
          f"{sum(len(d['utterances']) for d in STYLE_BANK.values())} utterances\n")

    # Select diverse clusters
    selected_clusters = select_diverse_clusters(STYLE_BANK, n=10)
    print(f"Selected {len(selected_clusters)} clusters for testing\n")

    # Generate scenarios
    scenarios = []

    print("=" * 80)
    print("생성된 시나리오")
    print("=" * 80)

    for i, (cluster_id, cluster_data) in enumerate(selected_clusters, 1):
        # Vary difficulty for diversity
        difficulties = ["happy", "happy", "edge", "edge", "happy",
                       "edge", "happy", "unhappy", "edge", "happy"]
        difficulty = difficulties[i - 1]

        scenario = generate_layer2_scenario(
            cluster_id=cluster_id,
            cluster_data=cluster_data,
            scenario_id=f"charan_layer2_{i:03d}",
            difficulty=difficulty
        )
        scenarios.append(scenario)

        # Display
        print(f"\n[{i}] {scenario['id']}")
        print(f"Intent: {scenario['intent']}")
        print(f"Difficulty: {scenario['difficulty_tier']}")
        print(f"Cluster: {cluster_id}")
        print(f"\n초기 발화 (실제 고객):")
        print(f'"{scenario["initial_message"]}"')
        print(f"\n길이: {scenario['metadata']['utterance_length']}자")
        print("-" * 80)

    # Summary statistics
    print("\n" + "=" * 80)
    print("통계")
    print("=" * 80)

    lengths = [s["metadata"]["utterance_length"] for s in scenarios]
    print(f"\n발화 길이:")
    print(f"  평균: {sum(lengths) / len(lengths):.1f}자")
    print(f"  최소: {min(lengths)}자")
    print(f"  최대: {max(lengths)}자")

    difficulty_counts = {}
    for s in scenarios:
        tier = s["difficulty_tier"]
        difficulty_counts[tier] = difficulty_counts.get(tier, 0) + 1

    print(f"\n난이도 분포:")
    for tier, count in sorted(difficulty_counts.items()):
        print(f"  {tier}: {count}개 ({count/len(scenarios)*100:.0f}%)")

    print(f"\n인텐트 다양성: {len(set(s['intent'] for s in scenarios))}개")

    # Save scenarios
    output = {
        "schema_version": "v0",
        "run_id": "charan-layer2-test",
        "generation_method": "layer2-utterance-transplant",
        "scenarios": scenarios,
        "generated_at": "2026-05-06T00:00:00Z",
        "generation_note": "Layer 2 test: 100% real customer utterances, no LLM generation"
    }

    output_path = Path("~/qa-agent/storage/layer2_test_scenarios.json").expanduser()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Scenarios saved to: {output_path}")
    print(f"   Total: {len(scenarios)} scenarios")
    print(f"   100% real customer utterances (0 LLM calls)")

    # Quality check
    print("\n" + "=" * 80)
    print("품질 체크")
    print("=" * 80)

    print("\n[자연스러움 샘플링]")
    sample_indices = [0, len(scenarios)//2, -1]  # First, middle, last

    for idx in sample_indices:
        s = scenarios[idx]
        msg = s["initial_message"]
        print(f"\n• Intent: {s['intent'][:30]}...")
        print(f"  \"{msg[:100]}{'...' if len(msg) > 100 else ''}\"")

        # Check natural markers
        markers = []
        if any(end in msg for end in ["요", "요?", "나요", "인가요"]):
            markers.append("구어체 어미")
        if any(p in msg for p in ["근데", "그럼", "혹시"]):
            markers.append("구어체 접속사")
        if "!" in msg or "?" in msg:
            markers.append("감정 표현")
        if not all(c.isspace() or ord(c) < 128 or c.isalnum() for c in msg.replace(" ", "")):
            # Check for spacing issues (natural typos)
            if "있어서" in msg or "해서" in msg:
                markers.append("자연스러운 띄어쓰기")

        print(f"  특징: {', '.join(markers) if markers else '중립적'}")

    print("\n" + "=" * 80)
    print("결론")
    print("=" * 80)
    print("""
✅ Layer 2 장점:
  - 100% 실제 고객 발화 (human-like 보장)
  - LLM 비용 $0
  - 자연스러운 구어체, 띄어쓰기, 감정 표현

⚠️ 제약사항:
  - 기존 발화 풀에만 의존 (새로운 edge case 생성 불가)
  - 다양성 = 클러스터당 utterance 개수에 비례

💡 권장:
  - Happy path: Layer 2 100% 사용
  - Edge case: Layer 1 (스타일 참고 생성) 혼용 고려
    """)


if __name__ == "__main__":
    main()
