"""Generate 3 separate scenario sets (Layer 1, 2, 3) with same 5 intents.

For actual ALF testing and transcript comparison.
"""

from pathlib import Path
import json
import random
from anthropic import Anthropic
import os
from dotenv import load_dotenv

# Load .env
load_dotenv(Path("~/qa-agent/.env").expanduser())

# Load style bank
STYLE_BANK_PATH = Path("~/qa-agent/storage/charan_style_bank.json").expanduser()

with open(STYLE_BANK_PATH, encoding="utf-8") as f:
    STYLE_BANK = json.load(f)

# Initialize Anthropic client
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://prism.ch.dev"
)

# Select 5 diverse intents
random.seed(42)
SELECTED_CLUSTERS = random.sample(list(STYLE_BANK.items()), 5)

print("=" * 80)
print("Layer 1, 2, 3 각 5개 시나리오 세트 생성 (동일 Intent)")
print("=" * 80)
print(f"\n선택된 Intent (5개):")
for i, (cid, data) in enumerate(SELECTED_CLUSTERS, 1):
    print(f"  {i}. {data['label']}")


# Layer 1: Style Reference Injection
def generate_layer1(intent: str, style_refs: list[str]) -> str:
    """Generate with style references."""
    prompt = f"""You are generating a QA scenario initial message.

### 실제 고객 발화 예시 (스타일 참고용)

{chr(10).join(f'{i}. "{ref}"' for i, ref in enumerate(style_refs[:3], 1))}

**중요**: 위 발화들의 말투, 문장 구조, 감정 표현 방식을 그대로 따라하세요.
- 어휘 선택
- 문장 길이와 끊김
- 이모티콘/강조 사용 패턴
- 감정 온도
- "안녕하세요" 같은 인사말 제거
- 짧게 (50~100자)

---

[생성할 시나리오]
Intent: {intent}

위 실제 대화의 "말하는 방식"을 그대로 따라하되, 내용은 intent에 맞게 작성하세요.

Output ONLY the customer message, nothing else."""

    response = client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


# Layer 2: Utterance Transplant
def generate_layer2(utterances: list[str], max_len: int = 80) -> str | None:
    """Select real utterance (shortest within length limit).

    Returns None if no utterance under max_len exists.
    This prevents timeout issues with ALF while maintaining natural speech.
    """
    valid = [u for u in utterances if len(u) <= max_len]
    if valid:
        return min(valid, key=len)
    return None


# Layer 3: Layer 1 + Validation
def validate_style(candidate: str, style_refs: list[str]) -> float:
    """Simple style similarity check."""
    score = 0.0
    avg_len = sum(len(ref) for ref in style_refs) / len(style_refs)
    if abs(len(candidate) - avg_len) < avg_len * 0.3:
        score += 0.3
    common_endings = ["요", "요?", "나요", "나요?", "인가요", "인가요?", "ㅠㅠ", "ㅜㅜ"]
    if any(candidate.endswith(end) for end in common_endings):
        score += 0.3
    formal_patterns = ["습니다", "드립니다", "겠습니다"]
    if not any(pattern in candidate for pattern in formal_patterns):
        score += 0.2
    casual_particles = ["근데", "그럼", "혹시", "아직"]
    if any(particle in candidate for particle in casual_particles):
        score += 0.2
    return min(score, 1.0)


def generate_layer3(intent: str, style_refs: list[str], max_retry: int = 2) -> str:
    """Layer 1 + validation loop."""
    for attempt in range(max_retry):
        candidate = generate_layer1(intent, style_refs)
        score = validate_style(candidate, style_refs)
        if score >= 0.7:
            return candidate
    return candidate


def create_scenario(scenario_id: str, intent: str, initial_msg: str,
                   cluster_id: str, layer: str) -> dict:
    """Create scenario dict."""
    return {
        "id": scenario_id,
        "intent": intent,
        "persona_ref": "polite_clear",
        "initial_message": initial_msg,
        "success_criteria": [],  # Will be filled by actual QA setup
        "max_turns": 6,
        "weight": 0.2,  # 5 scenarios = 1.0 total
        "difficulty_tier": "happy",
        "source": f"layer{layer}-test",
        "phase": "rag",
    }


def main():
    print("\n" + "=" * 80)
    print("생성 중...")
    print("=" * 80)

    layer1_scenarios = []
    layer2_scenarios = []
    layer3_scenarios = []

    for i, (cluster_id, cluster_data) in enumerate(SELECTED_CLUSTERS, 1):
        intent = cluster_data["label"]
        utterances = cluster_data["utterances"]

        print(f"\n[{i}/5] Intent: {intent[:50]}...")

        # Generate all 3 layers
        print("  - Layer 1...", end=" ")
        layer1_msg = generate_layer1(intent, utterances)
        layer1_scenarios.append(create_scenario(
            f"charan_layer1_{i:03d}", intent, layer1_msg, cluster_id, "1"
        ))
        print("✓")

        print("  - Layer 2...", end=" ")
        layer2_msg = generate_layer2(utterances, max_len=80)
        if layer2_msg is None:
            print("⚠️  (skipped: no utterance under 80 chars, fallback to Layer 1)")
            layer2_msg = layer1_msg
        else:
            print("✓")
        layer2_scenarios.append(create_scenario(
            f"charan_layer2_{i:03d}", intent, layer2_msg, cluster_id, "2"
        ))

        print("  - Layer 3...", end=" ")
        layer3_msg = generate_layer3(intent, utterances)
        layer3_scenarios.append(create_scenario(
            f"charan_layer3_{i:03d}", intent, layer3_msg, cluster_id, "3"
        ))
        print("✓")

    # Save 3 separate scenario sets
    output_dir = Path("~/qa-agent/storage/layer_test").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    for layer_num, scenarios in [("1", layer1_scenarios),
                                   ("2", layer2_scenarios),
                                   ("3", layer3_scenarios)]:
        scenario_set = {
            "schema_version": "v0",
            "run_id": f"charan-layer{layer_num}-test",
            "scenarios": scenarios,
            "generated_at": "2026-05-06T00:00:00Z",
            "generation_note": f"Layer {layer_num} test: 5 scenarios for actual ALF testing"
        }

        output_path = output_dir / f"scenarios_layer{layer_num}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(scenario_set, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Layer {layer_num} saved: {output_path}")

    # Summary comparison
    print("\n" + "=" * 80)
    print("시나리오 비교 (Initial Message)")
    print("=" * 80)

    for i in range(5):
        print(f"\n[{i+1}] {layer1_scenarios[i]['intent'][:40]}...")
        print(f"  Layer 1: \"{layer1_scenarios[i]['initial_message'][:80]}...\"")
        print(f"  Layer 2: \"{layer2_scenarios[i]['initial_message'][:80]}...\"")
        print(f"  Layer 3: \"{layer3_scenarios[i]['initial_message'][:80]}...\"")

    print("\n" + "=" * 80)
    print("다음 단계")
    print("=" * 80)
    print("""
1. Layer 1 테스트:
   cd ~/qa-agent && python3 -m tools.scenario_runner \\
       --scenarios storage/layer_test/scenarios_layer1.json \\
       --channel-url https://eoz6p.channel.io \\
       --output storage/layer_test/transcripts_layer1.jsonl

2. Layer 2 테스트:
   cd ~/qa-agent && python3 -m tools.scenario_runner \\
       --scenarios storage/layer_test/scenarios_layer2.json \\
       --channel-url https://eoz6p.channel.io \\
       --output storage/layer_test/transcripts_layer2.jsonl

3. Layer 3 테스트:
   cd ~/qa-agent && python3 -m tools.scenario_runner \\
       --scenarios storage/layer_test/scenarios_layer3.json \\
       --channel-url https://eoz6p.channel.io \\
       --output storage/layer_test/transcripts_layer3.jsonl

총 예상 시간: 약 25~30분
    """)


if __name__ == "__main__":
    main()
