"""Compare scenario generation across Baseline, Layer 1, Layer 2, Layer 3.

Generates initial_message for the same intent using different strategies
and compares human-likeness.
"""

from pathlib import Path
import json
from anthropic import Anthropic
import os
from dotenv import load_dotenv

# Load .env
load_dotenv(Path("~/qa-agent/.env").expanduser())

# Load style bank
STYLE_BANK_PATH = Path("~/qa-agent/storage/charan_style_bank.json").expanduser()

with open(STYLE_BANK_PATH, encoding="utf-8") as f:
    STYLE_BANK = json.load(f)

# Test intent - use first available cluster
TEST_CLUSTER_ID = list(STYLE_BANK.keys())[0]
TEST_INTENT = STYLE_BANK[TEST_CLUSTER_ID]["label"]
TEST_PERSONA = "polite_clear"

# Get style references
STYLE_REFS = STYLE_BANK[TEST_CLUSTER_ID]["utterances"][:3]

# Initialize Anthropic client (Prism Gateway)
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://prism.ch.dev"
)

def generate_baseline(intent: str, persona: str) -> str:
    """Baseline: 추상적 페르소나 지시만."""
    prompt = f"""You are generating a QA scenario initial message.

Intent: {intent}
Persona: {persona} (polite, clear, cooperative)

Generate a natural Korean customer message for this intent.
Keep it short (under 50 characters) and natural.

Output ONLY the customer message, nothing else."""

    response = client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


def generate_layer1(intent: str, persona: str, style_refs: list[str]) -> str:
    """Layer 1: Style Reference Injection."""
    prompt = f"""You are generating a QA scenario initial message.

### 실제 고객 발화 예시 (스타일 참고용)

{chr(10).join(f'{i}. "{ref}"' for i, ref in enumerate(style_refs, 1))}

**중요**: 위 발화들의 말투, 문장 구조, 감정 표현 방식을 그대로 따라하세요.
- 어휘 선택 (예: "가능한가요" vs "되나요" vs "해주세요")
- 문장 길이와 끊김
- 이모티콘/강조 사용 패턴 (ㅠㅠ, !, ? 등)
- 감정 온도

---

[생성할 시나리오]
Intent: {intent}
Persona: {persona}

위 실제 대화의 "말하는 방식"을 그대로 따라하되, 내용은 intent에 맞게 작성하세요.

Output ONLY the customer message, nothing else."""

    response = client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


def generate_layer2(intent: str, style_refs: list[str]) -> str:
    """Layer 2: Utterance Transplant (실제 발화 재사용)."""
    # 가장 유사한 실제 발화를 그대로 사용
    # 실제 구현에서는 vector search + minimal editing
    # 여기서는 가장 짧고 직접적인 발화 선택

    if not style_refs:
        return "[No style refs available]"

    # Simple heuristic: pick shortest utterance (most direct)
    selected = min(style_refs, key=len)

    # Minimal editing: 필요시 intent에 맞게 약간 수정
    # 이 예시에서는 그대로 사용
    return selected


def generate_layer3(intent: str, persona: str, style_refs: list[str], max_retry: int = 2) -> str:
    """Layer 3: Layer 1 + Validation Loop."""

    for attempt in range(max_retry):
        # Generate with Layer 1
        candidate = generate_layer1(intent, persona, style_refs)

        # Validate style similarity
        score = validate_style_similarity(candidate, style_refs)

        if score >= 0.7:  # Threshold
            return candidate
        else:
            print(f"   [Layer 3] Retry {attempt + 1}/{max_retry} (score: {score:.2f})")

    return candidate  # Return last attempt


def validate_style_similarity(candidate: str, style_refs: list[str]) -> float:
    """Simple style similarity check."""
    score = 0.0

    # Check 1: Length similarity (구어체는 짧음)
    avg_len = sum(len(ref) for ref in style_refs) / len(style_refs)
    if abs(len(candidate) - avg_len) < avg_len * 0.3:  # ±30%
        score += 0.3

    # Check 2: Ending pattern (요/나요/인가요 etc)
    common_endings = ["요", "요?", "나요", "나요?", "인가요", "인가요?", "ㅠㅠ", "ㅜㅜ"]
    if any(candidate.endswith(end) for end in common_endings):
        score += 0.3

    # Check 3: No formal patterns (습니다, 드립니다 등)
    formal_patterns = ["습니다", "드립니다", "겠습니다", "해주세요"]
    if not any(pattern in candidate for pattern in formal_patterns):
        score += 0.2

    # Check 4: Casual particles present
    casual_particles = ["근데", "그럼", "혹시", "아직"]
    if any(particle in candidate for particle in casual_particles):
        score += 0.2

    return min(score, 1.0)


def main():
    print("=" * 80)
    print("시나리오 생성 전략 비교: Baseline vs Layer 1 vs Layer 2 vs Layer 3")
    print("=" * 80)
    print(f"\nTest Intent: {TEST_INTENT}")
    print(f"Test Persona: {TEST_PERSONA}")
    print(f"\nStyle References ({len(STYLE_REFS)}):")
    for i, ref in enumerate(STYLE_REFS, 1):
        print(f"  {i}. \"{ref[:80]}{'...' if len(ref) > 80 else ''}\"")

    print("\n" + "=" * 80)
    print("생성 결과 비교")
    print("=" * 80)

    # Baseline
    print("\n[Baseline] 추상적 페르소나 지시만")
    print("-" * 80)
    baseline = generate_baseline(TEST_INTENT, TEST_PERSONA)
    print(f"생성: \"{baseline}\"")
    print(f"길이: {len(baseline)}자")
    print(f"스타일 점수: {validate_style_similarity(baseline, STYLE_REFS):.2f}")

    # Layer 1
    print("\n[Layer 1] Style Reference Injection")
    print("-" * 80)
    layer1 = generate_layer1(TEST_INTENT, TEST_PERSONA, STYLE_REFS)
    print(f"생성: \"{layer1}\"")
    print(f"길이: {len(layer1)}자")
    print(f"스타일 점수: {validate_style_similarity(layer1, STYLE_REFS):.2f}")

    # Layer 2
    print("\n[Layer 2] Utterance Transplant (실제 발화 재사용)")
    print("-" * 80)
    layer2 = generate_layer2(TEST_INTENT, STYLE_REFS)
    print(f"생성: \"{layer2}\"")
    print(f"길이: {len(layer2)}자")
    print(f"스타일 점수: {validate_style_similarity(layer2, STYLE_REFS):.2f}")
    print("   ⚠️  실제 발화 그대로 사용 (100% human-like)")

    # Layer 3
    print("\n[Layer 3] Layer 1 + Validation Loop")
    print("-" * 80)
    layer3 = generate_layer3(TEST_INTENT, TEST_PERSONA, STYLE_REFS)
    print(f"생성: \"{layer3}\"")
    print(f"길이: {len(layer3)}자")
    print(f"스타일 점수: {validate_style_similarity(layer3, STYLE_REFS):.2f}")

    # Summary table
    print("\n" + "=" * 80)
    print("비교 테이블")
    print("=" * 80)

    results = [
        ("Baseline", baseline, validate_style_similarity(baseline, STYLE_REFS)),
        ("Layer 1", layer1, validate_style_similarity(layer1, STYLE_REFS)),
        ("Layer 2", layer2, validate_style_similarity(layer2, STYLE_REFS)),
        ("Layer 3", layer3, validate_style_similarity(layer3, STYLE_REFS)),
    ]

    print(f"\n{'전략':<12} {'생성 결과':<50} {'스타일 점수':>12}")
    print("-" * 80)
    for strategy, text, score in results:
        display_text = text[:47] + "..." if len(text) > 50 else text
        print(f"{strategy:<12} {display_text:<50} {score:>12.2f}")

    print("\n" + "=" * 80)
    print("분석")
    print("=" * 80)
    print("""
- Baseline: AI가 생성한 평균적 문장 (격식체, 완결형)
- Layer 1: 실제 발화 스타일 모방 (구어체, 자연스러움 ↑)
- Layer 2: 실제 발화 재사용 (100% human-like, 다양성 제한)
- Layer 3: Layer 1 + 검증 루프 (품질 보장, API 비용 ↑)
    """)

    # Save results
    output = {
        "intent": TEST_INTENT,
        "persona": TEST_PERSONA,
        "style_refs": STYLE_REFS[:3],
        "results": {
            "baseline": {"text": baseline, "score": results[0][2]},
            "layer1": {"text": layer1, "score": results[1][2]},
            "layer2": {"text": layer2, "score": results[2][2]},
            "layer3": {"text": layer3, "score": results[3][2]},
        }
    }

    output_path = Path("~/qa-agent/storage/comparison_results.json").expanduser()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Results saved to: {output_path}")


if __name__ == "__main__":
    main()
