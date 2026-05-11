"""Generate and test scenarios with all 3 layers in one run.

For a given set of intents:
  1. Generate Layer 1, 2, 3 scenarios for each intent
  2. Test each scenario (1 intent × 3 layers) before moving to next
  3. Save results separately for each layer

This is more efficient than the old approach of:
  - Generate all layer1 → test all layer1
  - Generate all layer2 → test all layer2
  - Generate all layer3 → test all layer3

Usage:
    python3 run_3layer_test.py \
        --style-bank storage/charan_style_bank.json \
        --num-intents 5 \
        --channel-url https://eoz6p.channel.io \
        --output-dir storage/3layer_test \
        [--headed]
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

from tools.chat_driver import PlaywrightDriver
from tools.llm_client import create_llm_client, ProviderType
from tools.result_store import Scenario, Transcript
from tools.scenario_runner import run_one_scenario, PERSONA_FILE, LLM_BASE_URL, PERSONA_MODEL


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


async def test_scenario_3layers(
    intent: str,
    utterances: list[str],
    scenario_id_base: str,
    channel_url: str,
    llm_client,
    provider: ProviderType,
    persona_system_prompt: str,
    headed: bool,
    timeout: float,
) -> tuple[str, str | None, str, Transcript | None, Transcript | None, Transcript | None]:
    """Generate and test one intent with all 3 layers.

    Returns:
        (layer1_msg, layer2_msg, layer3_msg,
         layer1_transcript, layer2_transcript, layer3_transcript)
    """
    print(f"\n{'='*60}")
    print(f"Intent: {intent}")
    print(f"{'='*60}")

    # Generate messages
    print("Generating messages...")
    layer1_msg = generate_layer1(intent, utterances)
    print(f"  Layer 1: \"{layer1_msg}\"")

    layer2_msg = generate_layer2(utterances, max_len=80)
    if layer2_msg is None:
        print(f"  Layer 2: ⚠️  skipped (no utterance under 80 chars, fallback to Layer 1)")
        layer2_msg = layer1_msg
    else:
        print(f"  Layer 2: \"{layer2_msg}\"")

    layer3_msg = generate_layer3(intent, utterances)
    print(f"  Layer 3: \"{layer3_msg}\"")

    # Test all 3 layers
    transcripts = []
    for layer_num, layer_msg in [(1, layer1_msg), (2, layer2_msg), (3, layer3_msg)]:
        print(f"\nTesting Layer {layer_num}...")

        scenario = Scenario(
            id=f"{scenario_id_base}_layer{layer_num}",
            intent=intent,
            persona_ref="polite_clear",
            initial_message=layer_msg,
            success_criteria=[],
            max_turns=6,
            weight=0.2,
            difficulty_tier="happy",
            source=f"3layer-test-layer{layer_num}",
            phase="rag",
        )

        try:
            transcript = await run_one_scenario(
                scenario,
                channel_url=channel_url,
                run_id=f"3layer-test-layer{layer_num}",
                llm_client=llm_client,
                provider=provider,
                model=PERSONA_MODEL,
                persona_system_prompt=persona_system_prompt,
                client_tone=None,
                headed=headed,
                timeout=timeout,
            )
            transcripts.append(transcript)
            print(f"  → {transcript.terminated_reason} ({len(transcript.turns)} turns)")
        except Exception as e:
            print(f"  → ERROR: {e}")
            transcripts.append(None)

        # Delay between layers
        await asyncio.sleep(2)

    return (layer1_msg, layer2_msg, layer3_msg, *transcripts)


async def main_async(args):
    """Main async entry point."""
    # Load style bank
    style_bank_path = Path(args.style_bank).expanduser()
    with open(style_bank_path, encoding="utf-8") as f:
        style_bank = json.load(f)

    # Load best practices if provided
    best_practice_records = []
    if args.best_practice:
        from tools.best_practice_loader import load_best_practices

        bp_path = Path(args.best_practice).expanduser()
        best_practice_records = load_best_practices(
            bp_path,
            priority_only=args.bp_priority_only,
            rag_only=args.bp_rag_only,
        )
        print(f"Loaded {len(best_practice_records)} best practice records")

    # Select random intents (with replacement if num_intents > available clusters)
    random.seed(42)
    all_clusters = list(style_bank.items())
    if args.num_intents <= len(all_clusters):
        selected_clusters = random.sample(all_clusters, args.num_intents)
    else:
        # Allow duplicates when requesting more intents than available
        selected_clusters = random.choices(all_clusters, k=args.num_intents)

    print(f"{'='*60}")
    print(f"3-Layer Test Run")
    print(f"{'='*60}")
    print(f"Random Intents: {args.num_intents}")
    if best_practice_records:
        print(f"Best Practice: {len(best_practice_records)}")
        print(f"  - Priority only: {args.bp_priority_only}")
        print(f"  - RAG only: {args.bp_rag_only}")
    print(f"Channel: {args.channel_url}")
    print(f"Output: {args.output_dir}")
    print()

    print("Random Intents:")
    for i, (cluster_id, data) in enumerate(selected_clusters, 1):
        print(f"  [{i}/{args.num_intents}] {data['label']}")

    if best_practice_records:
        print()
        print("Best Practice Cases:")
        for i, bp in enumerate(best_practice_records[:10], 1):
            print(f"  [{i}] {bp.intent[:60]}...")
            if i == 10 and len(best_practice_records) > 10:
                print(f"  ... and {len(best_practice_records) - 10} more")

    # Setup
    llm_client, model, provider = create_llm_client()
    persona_system_prompt = PERSONA_FILE.read_text(encoding="utf-8")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Storage for results
    results = {
        "layer1": {"messages": [], "transcripts": []},
        "layer2": {"messages": [], "transcripts": []},
        "layer3": {"messages": [], "transcripts": []},
    }

    # Test random intents with all 3 layers
    for i, (cluster_id, cluster_data) in enumerate(selected_clusters, 1):
        intent = cluster_data["label"]
        utterances = cluster_data["utterances"]

        layer1_msg, layer2_msg, layer3_msg, t1, t2, t3 = await test_scenario_3layers(
            intent=intent,
            utterances=utterances,
            scenario_id_base=f"random_{i:03d}",
            channel_url=args.channel_url,
            llm_client=llm_client,
            provider=provider,
            persona_system_prompt=persona_system_prompt,
            headed=args.headed,
            timeout=args.timeout,
        )

        # Store results
        results["layer1"]["messages"].append(layer1_msg)
        results["layer1"]["transcripts"].append(t1)
        results["layer2"]["messages"].append(layer2_msg)
        results["layer2"]["transcripts"].append(t2)
        results["layer3"]["messages"].append(layer3_msg)
        results["layer3"]["transcripts"].append(t3)

    # Test best practice cases
    if best_practice_records:
        print("\n" + "="*60)
        print("Testing Best Practice Cases")
        print("="*60)

        for i, bp in enumerate(best_practice_records, 1):
            print(f"\n[{i}/{len(best_practice_records)}] {bp.intent[:60]}...")
            print(f"  URL: {bp.url}")
            print(f"  Classification: {bp.classification}")

            # TODO: Extract actual initial message from UserChat URL
            # For now, use intent as placeholder
            initial_msg_placeholder = f"[Best Practice] {bp.intent}"

            # Find matching cluster in style bank for style reference
            matching_cluster = None
            for cluster_id, cluster_data in style_bank.items():
                if bp.subcategory in cluster_data["label"] or bp.intent[:20] in cluster_data["label"]:
                    matching_cluster = cluster_data
                    break

            if not matching_cluster:
                # Use first cluster as fallback
                matching_cluster = list(style_bank.values())[0]

            utterances = matching_cluster["utterances"]

            # Generate Layer 1 and 3 (Layer 2 = use placeholder initial message)
            layer1_msg = generate_layer1(bp.intent, utterances)
            layer2_msg = initial_msg_placeholder  # TODO: Extract real message
            layer3_msg = generate_layer3(bp.intent, utterances)

            print(f"  Layer 1: \"{layer1_msg[:60]}...\"")
            print(f"  Layer 2: \"{layer2_msg[:60]}...\"")
            print(f"  Layer 3: \"{layer3_msg[:60]}...\"")

            # Test all 3 layers
            for layer_num, layer_msg in [(1, layer1_msg), (2, layer2_msg), (3, layer3_msg)]:
                print(f"\n  Testing Layer {layer_num}...")

                scenario = Scenario(
                    id=f"bp_{bp.user_chat_id[:8]}_layer{layer_num}",
                    intent=bp.intent,
                    persona_ref="polite_clear",
                    initial_message=layer_msg,
                    success_criteria=[],
                    max_turns=6,
                    weight=0.2,
                    difficulty_tier="happy",
                    source=f"best-practice-layer{layer_num}",
                    phase="rag",
                )

                try:
                    transcript = await run_one_scenario(
                        scenario,
                        channel_url=args.channel_url,
                        run_id=f"best-practice-layer{layer_num}",
                        llm_client=llm_client,
                        provider=provider,
                        model=PERSONA_MODEL,
                        persona_system_prompt=persona_system_prompt,
                        client_tone=None,
                        headed=args.headed,
                        timeout=args.timeout,
                    )
                    results[f"layer{layer_num}"]["transcripts"].append(transcript)
                    print(f"    → {transcript.terminated_reason} ({len(transcript.turns)} turns)")
                except Exception as e:
                    print(f"    → ERROR: {e}")

                # Delay between layers
                await asyncio.sleep(2)

    # Save transcripts
    from dataclasses import asdict

    for layer_name in ["layer1", "layer2", "layer3"]:
        transcripts = [t for t in results[layer_name]["transcripts"] if t is not None]
        if not transcripts:
            continue

        output_path = output_dir / f"transcripts_{layer_name}.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for t in transcripts:
                json.dump(asdict(t), f, ensure_ascii=False)
                f.write("\n")

        print(f"\n✅ {layer_name}: {len(transcripts)} transcripts → {output_path}")

    # Save summary
    summary = {
        "run_at": datetime.now().isoformat(),
        "num_intents": args.num_intents,
        "channel_url": args.channel_url,
        "results": {
            layer: {
                "total": len(results[layer]["transcripts"]),
                "completed": sum(1 for t in results[layer]["transcripts"]
                                if t and t.terminated_reason == "completed"),
                "timeout": sum(1 for t in results[layer]["transcripts"]
                              if t and t.terminated_reason == "timeout"),
                "error": sum(1 for t in results[layer]["transcripts"]
                            if t and t.terminated_reason == "error"),
            }
            for layer in ["layer1", "layer2", "layer3"]
        }
    }

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Summary → {summary_path}")
    print("\n" + "="*60)
    print("Done!")
    print("="*60)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Generate and test scenarios with all 3 layers"
    )
    parser.add_argument(
        "--style-bank",
        required=True,
        help="Path to style bank JSON (e.g., storage/charan_style_bank.json)",
    )
    parser.add_argument(
        "--num-intents",
        type=int,
        default=5,
        help="Number of intents to test (default: 5)",
    )
    parser.add_argument(
        "--best-practice",
        help="Path to best practice Excel file (e.g., ~/Downloads/차란 - Best Practice.xlsx)",
    )
    parser.add_argument(
        "--bp-priority-only",
        action="store_true",
        help="Use only ⭐ priority best practices",
    )
    parser.add_argument(
        "--bp-rag-only",
        action="store_true",
        help="Use only 🟢 RAG best practices (no admin dependency)",
    )
    parser.add_argument(
        "--channel-url",
        required=True,
        help="Channel.io URL (e.g., https://eoz6p.channel.io)",
    )
    parser.add_argument(
        "--output-dir",
        default="storage/3layer_test",
        help="Output directory for transcripts (default: storage/3layer_test)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="ALF reply timeout in seconds (default: 120)",
    )

    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
