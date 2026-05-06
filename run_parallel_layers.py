"""Run Layer 1, 2, 3 tests in parallel for each scenario.

For each scenario intent:
  1. Generate 3 versions (Layer 1, 2, 3)
  2. Run all 3 in parallel against ALF
  3. Compare results

This replaces the sequential "run layer1, run layer2, run layer3" approach
with a more efficient parallel execution strategy.

Usage:
    python3 run_parallel_layers.py --scenarios <path> --channel-url <url> [--headed]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

from tools.chat_driver import PlaywrightDriver
from tools.llm_client import create_llm_client, ProviderType
from tools.result_store import (
    Scenario,
    Transcript,
    append_transcript,
    read_scenarios,
)
from tools.scenario_runner import run_one_scenario, PERSONA_FILE, LLM_BASE_URL, PERSONA_MODEL


async def run_scenario_all_layers(
    scenario: Scenario,
    channel_url: str,
    llm_client,
    provider: ProviderType,
    model: str,
    persona_system_prompt: str,
    headed: bool,
    timeout: float,
) -> tuple[Transcript, Transcript, Transcript]:
    """Run one scenario with all 3 layers sequentially.

    Note: Cannot run in true parallel because multiple browsers on same channel
    would interfere with each other. "Parallel" here means running all 3 layers
    for each scenario before moving to the next scenario.

    Returns: (layer1_transcript, layer2_transcript, layer3_transcript)
    """
    run_id_base = scenario.id.rsplit("_", 1)[0]  # e.g., "charan_layer1" -> "charan"
    scenario_num = scenario.id.rsplit("_", 1)[1]  # e.g., "001"

    transcripts = []
    for layer_num in [1, 2, 3]:
        layer_scenario = Scenario(
            id=f"{run_id_base}_layer{layer_num}_{scenario_num}",
            intent=scenario.intent,
            persona_ref=scenario.persona_ref,
            initial_message=scenario.initial_message,
            success_criteria=scenario.success_criteria,
            max_turns=scenario.max_turns,
            weight=scenario.weight,
            difficulty_tier=scenario.difficulty_tier,
            source=f"layer{layer_num}-parallel",
            phase=scenario.phase,
        )

        try:
            transcript = await run_one_scenario(
                layer_scenario,
                channel_url=channel_url,
                run_id=f"parallel-layer{layer_num}",
                llm_client=llm_client,
                provider=provider,
                model=model,
                persona_system_prompt=persona_system_prompt,
                client_tone=None,
                headed=headed,
                timeout=timeout,
            )
            transcripts.append(transcript)
        except Exception as e:
            print(f"  Layer {layer_num} error: {e}")
            transcripts.append(None)

        # Small delay between layers to avoid channel interference
        await asyncio.sleep(1)

    return tuple(transcripts)


async def main_async(args):
    """Main async entry point."""
    scenarios_path = Path(args.scenarios).expanduser()
    if not scenarios_path.exists():
        print(f"Error: scenarios file not found: {scenarios_path}")
        return 1

    with open(scenarios_path, encoding="utf-8") as f:
        data = json.load(f)

    scenarios = [
        Scenario(
            id=s["id"],
            intent=s["intent"],
            persona_ref=s["persona_ref"],
            initial_message=s["initial_message"],
            success_criteria=s.get("success_criteria", []),
            max_turns=s["max_turns"],
            weight=s["weight"],
            difficulty_tier=s["difficulty_tier"],
            source=s.get("source", "unknown"),
            phase=s.get("phase", "rag"),
        )
        for s in data["scenarios"]
    ]

    # LLM client setup
    llm_client = create_llm_client(base_url=LLM_BASE_URL)
    provider = ProviderType.ANTHROPIC

    persona_system_prompt = PERSONA_FILE.read_text(encoding="utf-8")

    print(f"[parallel runner] scenarios={len(scenarios)} channel={args.channel_url}")
    print(f"[parallel runner] Running {len(scenarios)} scenarios × 3 layers in parallel\n")

    output_dir = Path("~/qa-agent/storage/parallel_test").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_transcripts = {"layer1": [], "layer2": [], "layer3": []}

    for i, scenario in enumerate(scenarios, 1):
        print(f"[{i}/{len(scenarios)}] {scenario.id} ({scenario.intent[:40]}...)")
        print(f"  Initial: \"{scenario.initial_message[:60]}...\"")

        try:
            layer1_t, layer2_t, layer3_t = await run_scenario_all_layers(
                scenario,
                channel_url=args.channel_url,
                llm_client=llm_client,
                provider=provider,
                model=PERSONA_MODEL,
                persona_system_prompt=persona_system_prompt,
                headed=args.headed,
                timeout=args.timeout,
            )

            # Store transcripts
            if layer1_t:
                all_transcripts["layer1"].append(layer1_t)
                print(f"  Layer 1: {layer1_t.terminated_reason} ({len(layer1_t.turns)} turns)")
            if layer2_t:
                all_transcripts["layer2"].append(layer2_t)
                print(f"  Layer 2: {layer2_t.terminated_reason} ({len(layer2_t.turns)} turns)")
            if layer3_t:
                all_transcripts["layer3"].append(layer3_t)
                print(f"  Layer 3: {layer3_t.terminated_reason} ({len(layer3_t.turns)} turns)")

            print()

        except Exception as e:
            print(f"  ERROR: {e}\n")
            continue

        # Rate limiting: wait between scenario batches
        if i < len(scenarios):
            await asyncio.sleep(2)

    # Save transcripts
    for layer_name, transcripts in all_transcripts.items():
        if not transcripts:
            continue

        output_path = output_dir / f"transcripts_{layer_name}.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for t in transcripts:
                json.dump(t.__dict__, f, ensure_ascii=False)
                f.write("\n")

        print(f"[parallel runner] {layer_name}: {len(transcripts)} transcripts → {output_path}")

    print("\n[parallel runner] Done!")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Run Layer 1/2/3 in parallel for each scenario"
    )
    parser.add_argument(
        "--scenarios",
        required=True,
        help="Path to scenarios.json (any layer, will run all 3)",
    )
    parser.add_argument(
        "--channel-url",
        required=True,
        help="Channel.io URL (e.g., https://eoz6p.channel.io)",
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
