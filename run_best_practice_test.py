"""Test best practice user chats with randomly selected layer (1, 2, or 3).

For each best practice case:
  1. Load from Excel
  2. Randomly select one layer (1, 2, or 3)
  3. Generate message for that layer
  4. Test against ALF

Usage:
    python3 run_best_practice_test.py \
        --best-practice "~/Downloads/차란 - Best Practice.xlsx" \
        --style-bank storage/charan_style_bank_100.json \
        --priority-only \
        --rag-only \
        --channel-url https://eoz6p.channel.io \
        --output-dir storage/bp_test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path
from datetime import datetime

from anthropic import Anthropic
from dotenv import load_dotenv

from tools.best_practice_loader import load_best_practices
from tools.llm_client import create_llm_client, ProviderType
from tools.result_store import Scenario, Transcript
from tools.scenario_runner import run_one_scenario, PERSONA_FILE, PERSONA_MODEL


# Load .env
load_dotenv(Path("~/qa-agent/.env").expanduser())

# Initialize Anthropic client for scenario generation
anthropic_client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://prism.ch.dev"
)


def generate_layer1(intent: str, style_refs: list[str]) -> str:
    """Layer 1: Style Reference Injection (LLM with few-shot)."""
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

    response = anthropic_client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


def generate_layer2(utterances: list[str], max_len: int = 80) -> str | None:
    """Layer 2: Utterance Transplant (real customer utterance).

    Returns None if no utterance under max_len exists.
    """
    valid = [u for u in utterances if len(u) <= max_len]
    if valid:
        return min(valid, key=len)
    return None


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
    """Layer 3: Layer 1 + Validation."""
    for attempt in range(max_retry):
        candidate = generate_layer1(intent, style_refs)
        score = validate_style(candidate, style_refs)
        if score >= 0.7:
            return candidate
    return candidate


async def test_best_practice(
    bp_record,
    layer_num: int,
    style_bank: dict,
    channel_url: str,
    llm_client,
    provider: ProviderType,
    persona_system_prompt: str,
    headed: bool,
    timeout: float,
) -> tuple[str, Transcript | None]:
    """Test one best practice with selected layer.

    Returns:
        (initial_message, transcript)
    """
    # Find matching cluster for style reference
    matching_cluster = None
    for cluster_id, cluster_data in style_bank.items():
        if (bp_record.subcategory in cluster_data["label"] or
            bp_record.intent[:20] in cluster_data["label"]):
            matching_cluster = cluster_data
            break

    if not matching_cluster:
        # Use first cluster as fallback
        matching_cluster = list(style_bank.values())[0]

    utterances = matching_cluster["utterances"]

    # Generate message based on layer
    if layer_num == 1:
        initial_msg = generate_layer1(bp_record.intent, utterances)
    elif layer_num == 2:
        initial_msg = generate_layer2(utterances, max_len=80)
        if initial_msg is None:
            # Fallback to Layer 1
            initial_msg = generate_layer1(bp_record.intent, utterances)
            print(f"    ⚠️  Layer 2 fallback to Layer 1")
    else:  # layer_num == 3
        initial_msg = generate_layer3(bp_record.intent, utterances)

    print(f"    Message: \"{initial_msg[:80]}...\"")

    # Create scenario
    scenario = Scenario(
        id=f"bp_{bp_record.user_chat_id[:8]}_layer{layer_num}",
        intent=bp_record.intent,
        persona_ref="polite_clear",
        initial_message=initial_msg,
        success_criteria=[],
        max_turns=6,
        weight=0.2,
        difficulty_tier="happy",
        source=f"best-practice-layer{layer_num}",
        phase="rag",
    )

    # Test
    try:
        transcript = await run_one_scenario(
            scenario,
            channel_url=channel_url,
            run_id=f"best-practice-layer{layer_num}",
            llm_client=llm_client,
            provider=provider,
            model=PERSONA_MODEL,
            persona_system_prompt=persona_system_prompt,
            client_tone=None,
            headed=headed,
            timeout=timeout,
        )
        return (initial_msg, transcript)
    except Exception as e:
        print(f"    ERROR: {e}")
        return (initial_msg, None)


async def main_async(args):
    """Main async entry point."""
    # Load best practices
    bp_path = Path(args.best_practice).expanduser()
    bp_records = load_best_practices(
        bp_path,
        priority_only=args.priority_only,
        rag_only=args.rag_only,
        bot_only=args.bot_only,
    )

    # Load style bank
    style_bank_path = Path(args.style_bank).expanduser()
    with open(style_bank_path, encoding="utf-8") as f:
        style_bank = json.load(f)

    print(f"{'='*60}")
    print(f"Best Practice Test Run")
    print(f"{'='*60}")
    print(f"Best Practices: {len(bp_records)}")
    print(f"  - Priority only: {args.priority_only}")
    print(f"  - RAG only: {args.rag_only}")
    print(f"  - Bot only: {args.bot_only}")
    print(f"Channel: {args.channel_url}")
    print(f"Output: {args.output_dir}")
    print(f"Random Layer Selection: Enabled")
    print()

    # Setup
    llm_client, model, provider = create_llm_client()
    persona_system_prompt = PERSONA_FILE.read_text(encoding="utf-8")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Storage for results
    results = []
    layer_counts = {1: 0, 2: 0, 3: 0}

    # Test each best practice
    for i, bp in enumerate(bp_records, 1):
        # Randomly select layer (1, 2, or 3)
        layer_num = random.choice([1, 2, 3])
        layer_counts[layer_num] += 1

        print(f"\n{'='*60}")
        print(f"[{i}/{len(bp_records)}] {bp.intent[:60]}...")
        print(f"{'='*60}")
        print(f"  UserChat ID: {bp.user_chat_id}")
        print(f"  Classification: {bp.classification}")
        print(f"  Responder: {bp.responder}")
        print(f"  Selected Layer: {layer_num}")

        initial_msg, transcript = await test_best_practice(
            bp_record=bp,
            layer_num=layer_num,
            style_bank=style_bank,
            channel_url=args.channel_url,
            llm_client=llm_client,
            provider=provider,
            persona_system_prompt=persona_system_prompt,
            headed=args.headed,
            timeout=args.timeout,
        )

        if transcript:
            print(f"    → {transcript.terminated_reason} ({len(transcript.turns)} turns)")
            results.append({
                "bp_url": bp.url,
                "bp_intent": bp.intent,
                "bp_classification": bp.classification,
                "layer": layer_num,
                "initial_message": initial_msg,
                "transcript": transcript,
            })
        else:
            print(f"    → Failed")

        # Delay between tests
        await asyncio.sleep(2)

    # Save results
    from dataclasses import asdict

    output_path = output_dir / "transcripts.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            record = {
                "bp_url": r["bp_url"],
                "bp_intent": r["bp_intent"],
                "bp_classification": r["bp_classification"],
                "layer": r["layer"],
                "initial_message": r["initial_message"],
                "transcript": asdict(r["transcript"]),
            }
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")

    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    print(f"Total tested: {len(results)}/{len(bp_records)}")
    print(f"Layer distribution:")
    print(f"  Layer 1: {layer_counts[1]}")
    print(f"  Layer 2: {layer_counts[2]}")
    print(f"  Layer 3: {layer_counts[3]}")
    print(f"\n✅ Results saved to: {output_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Test best practice cases with random layer selection"
    )
    parser.add_argument(
        "--best-practice",
        required=True,
        help="Path to best practice Excel (e.g., ~/Downloads/차란 - Best Practice.xlsx)",
    )
    parser.add_argument(
        "--style-bank",
        required=True,
        help="Path to style bank JSON",
    )
    parser.add_argument(
        "--priority-only",
        action="store_true",
        help="Test only ⭐ priority cases",
    )
    parser.add_argument(
        "--rag-only",
        action="store_true",
        help="Test only 🟢 RAG cases",
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Test only cases handled by bot alone",
    )
    parser.add_argument(
        "--channel-url",
        required=True,
        help="Channel.io URL",
    )
    parser.add_argument(
        "--output-dir",
        default="storage/bp_test",
        help="Output directory",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="ALF reply timeout in seconds",
    )

    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
