"""Run complete Best Practice QA pipeline from sop-agent clustering results.

Workflow:
  1. Extract Best Practice cases from clustering (tools/best_practice_extractor.py)
  2. Generate QA scenarios with Layer 1/2/3 (tools/scenario_generator.py)
  3. Execute QA tests via Playwright (tools/scenario_runner.py)
  4. Generate HTML/MD reports with BP comparison (tools/integrated_report_generator.py)

Usage:
    python3 run_bp_qa.py \
        --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
        --channel-url https://eoz6p.channel.io \
        --output-dir storage/qa_$(date +%Y%m%d) \
        --target-total 100
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

from tools.best_practice_extractor import extract_best_practices, BestPracticeCase
from tools.llm_client import create_llm_client, ProviderType
from tools.result_store import Scenario, Transcript
from tools.scenario_runner import run_one_scenario, PERSONA_FILE, PERSONA_MODEL
from tools.bp_qa_report_generator import generate_bp_qa_reports
import pandas as pd


# Load .env
REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

# Initialize Anthropic client for scenario generation
anthropic_client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://prism.ch.dev"
)


def generate_layer1(intent: str, enhanced_text: str) -> str:
    """Layer 1: LLM generation with style reference from BP text."""
    # Extract first 200 chars of BP text as style reference
    style_ref = enhanced_text[:200].replace("\n", " ").strip()

    prompt = f"""You are generating a customer inquiry message for QA testing.

### Context (Best Practice style reference)
Original conversation style:
"{style_ref}..."

### Task
Generate a natural customer inquiry message that matches:
- Intent: {intent}
- Style: Similar tone and phrasing to the reference above

Requirements:
- Natural Korean customer speech
- 30-80 characters
- No greetings like "안녕하세요"
- Direct inquiry only

Output ONLY the customer message, nothing else."""

    response = anthropic_client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


def generate_layer2(enhanced_text: str, max_len: int = 80) -> str | None:
    """Layer 2: Extract first user utterance from BP enhanced_text.

    Returns None if extraction fails or utterance is too long.
    """
    # Parse enhanced_text which contains conversation turns
    # Format: "USER: message\nALF: response\n..."
    lines = enhanced_text.split("\n")
    for line in lines:
        if line.startswith("USER:") or line.startswith("고객:"):
            utterance = line.split(":", 1)[1].strip()
            # Remove common greetings
            utterance = utterance.replace("안녕하세요", "").replace("안녕하세요.", "").strip()
            if utterance and len(utterance) <= max_len:
                return utterance
    return None


def generate_layer3(intent: str, enhanced_text: str, max_retry: int = 2) -> str:
    """Layer 3: Layer 1 + simple validation."""
    for attempt in range(max_retry):
        candidate = generate_layer1(intent, enhanced_text)
        # Simple validation: not too short, not too long
        if 20 <= len(candidate) <= 100:
            return candidate
    return candidate


def load_manual_bp(manual_bp_file: Path, clustered_excel: Path) -> list[BestPracticeCase]:
    """Load manually specified Best Practice cases.

    Manual BP file format (TSV or CSV):
    - Required columns: user_chat_id or url
    - Optional columns: intent, category

    Looks up full details from clustering Excel.
    """
    # Read manual BP file
    if not manual_bp_file.exists():
        raise FileNotFoundError(f"Manual BP file not found: {manual_bp_file}")

    suffix = manual_bp_file.suffix.lower()
    if suffix == '.tsv':
        manual_df = pd.read_csv(manual_bp_file, sep='\t')
    elif suffix in ['.csv', '.txt']:
        manual_df = pd.read_csv(manual_bp_file)
    elif suffix in ['.xlsx', '.xls']:
        manual_df = pd.read_excel(manual_bp_file)
    else:
        raise ValueError(f"Unsupported manual BP file format: {suffix}")

    # Extract user_chat_ids
    user_chat_ids = set()
    if 'user_chat_id' in manual_df.columns:
        user_chat_ids.update(manual_df['user_chat_id'].dropna().astype(str))
    if 'url' in manual_df.columns:
        for url in manual_df['url'].dropna():
            # Extract ID from URL: https://desk.channel.io/.../user-chats/{id}
            import re
            match = re.search(r'/user-chats/([a-f0-9]+)', str(url))
            if match:
                user_chat_ids.add(match.group(1))

    if not user_chat_ids:
        raise ValueError("Manual BP file must contain 'user_chat_id' or 'url' column")

    print(f"📋 Manual BP: {len(user_chat_ids)} user chat IDs specified")

    # Load clustering data
    if not clustered_excel.exists():
        raise FileNotFoundError(f"Clustering Excel not found: {clustered_excel}")

    cluster_df = pd.read_excel(clustered_excel)
    cluster_df = cluster_df[cluster_df['cluster_id'].notna()].copy()

    # Match by user_chat_id
    cluster_df['id_str'] = cluster_df['id'].astype(str)
    matched_df = cluster_df[cluster_df['id_str'].isin(user_chat_ids)]

    if len(matched_df) == 0:
        raise ValueError(f"No matching user chats found in clustering Excel. "
                        f"Specified IDs: {list(user_chat_ids)[:5]}...")

    print(f"✓ Matched {len(matched_df)}/{len(user_chat_ids)} cases in clustering data")

    # Get cluster sizes
    cluster_sizes = cluster_df.groupby('cluster_id').size()

    # Convert to BestPracticeCase
    bp_cases = []
    for _, row in matched_df.iterrows():
        case = BestPracticeCase(
            user_chat_id=row['id'],
            user_chat_url=row['url'],
            cluster_id=int(row['cluster_id']),
            cluster_label=row['label'] if pd.notna(row['label']) else f"Cluster {row['cluster_id']}",
            cluster_category=row['category'] if pd.notna(row['category']) else "기타",
            cluster_size=int(cluster_sizes[row['cluster_id']]),
            enhanced_text=row['enhanced_text'] if pd.notna(row['enhanced_text']) else "",
            tags=str(row['tags']).split(',') if pd.notna(row['tags']) else [],
            priority=row['priority'] if pd.notna(row['priority']) else "medium",
            state=row['state'] if pd.notna(row['state']) else "unknown",
            csat=float(row['profile.csat']) if pd.notna(row['profile.csat']) else None,
            alf_triggered=bool(row['alfTriggered']) if pd.notna(row['alfTriggered']) else False,
            time_to_first_answer=float(row['timeToFirstAnswer']) if pd.notna(row['timeToFirstAnswer']) else None,
            reply_count=int(row['replyCount']) if pd.notna(row['replyCount']) else 0,
        )
        bp_cases.append(case)

    return bp_cases


async def generate_and_test_bp_case(
    bp_case: BestPracticeCase,
    layer_num: int,
    channel_url: str,
    llm_client,
    provider: ProviderType,
    persona_system_prompt: str,
    headed: bool,
    timeout: float,
) -> tuple[str, Transcript | None]:
    """Generate scenario and test one Best Practice case.

    Returns:
        (initial_message, transcript)
    """
    # Generate message based on layer
    if layer_num == 1:
        initial_msg = generate_layer1(bp_case.intent, bp_case.enhanced_text)
    elif layer_num == 2:
        initial_msg = generate_layer2(bp_case.enhanced_text, max_len=80)
        if initial_msg is None:
            # Fallback to Layer 1
            initial_msg = generate_layer1(bp_case.intent, bp_case.enhanced_text)
            print(f"    ⚠️  Layer 2 fallback to Layer 1")
    else:  # layer_num == 3
        initial_msg = generate_layer3(bp_case.intent, bp_case.enhanced_text)

    print(f"    Message: \"{initial_msg[:80]}...\"" if len(initial_msg) > 80 else f"    Message: \"{initial_msg}\"")

    # Create scenario
    scenario = Scenario(
        id=f"bp_{bp_case.user_chat_id[:8]}_c{bp_case.cluster_id}_layer{layer_num}",
        intent=bp_case.intent,
        persona_ref="polite_clear",
        initial_message=initial_msg,
        success_criteria=[],
        max_turns=6,
        weight=0.2,
        difficulty_tier="happy",
        source=f"bp-clustering-layer{layer_num}",
        phase="rag",
    )

    # Test
    try:
        transcript = await run_one_scenario(
            scenario,
            channel_url=channel_url,
            run_id=f"bp-clustering-layer{layer_num}",
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
    # Step 1: Extract Best Practice cases
    clustered_excel = Path(args.clustered_excel).expanduser()
    print(f"{'='*70}")
    print(f"Step 1: Extract Best Practice")
    print(f"{'='*70}")

    if args.manual_bp:
        # Manual BP selection
        manual_bp_file = Path(args.manual_bp).expanduser()
        print(f"Mode: Manual selection")
        print(f"Manual BP file: {manual_bp_file}")
        print(f"Clustered Excel: {clustered_excel}")
        print()

        bp_cases = load_manual_bp(manual_bp_file, clustered_excel)
    else:
        # Automatic extraction from clustering
        print(f"Mode: Automatic extraction from clustering")
        print(f"Clustered Excel: {clustered_excel}")
        print(f"Target cases: {args.target_total}")
        print()

        bp_cases = extract_best_practices(
            clustered_excel=clustered_excel,
            target_total=args.target_total,
            filters={
                "min_cluster_size": args.min_cluster_size,
                "require_alf": False,
                "max_per_cluster": args.max_per_cluster,
            }
        )

    print(f"✅ Extracted {len(bp_cases)} Best Practice cases")
    from collections import Counter
    cat_counts = Counter(c.category_display for c in bp_cases)
    print(f"\nDistribution by category:")
    for cat, count in cat_counts.most_common():
        print(f"  {cat}: {count}")
    print()

    # Step 2: Generate and test scenarios
    print(f"{'='*70}")
    print(f"Step 2-3: Generate scenarios + Execute QA")
    print(f"{'='*70}")
    print(f"Channel: {args.channel_url}")
    print(f"Output: {args.output_dir}")
    print(f"Layer strategy: {args.layer_strategy}")
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
    for i, bp_case in enumerate(bp_cases, 1):
        # Select layer based on strategy
        if args.layer_strategy == "random":
            layer_num = random.choice([1, 2, 3])
        elif args.layer_strategy == "balanced":
            # Ensure equal distribution
            layer_num = ((i - 1) % 3) + 1
        else:
            # Specific layer: "layer1", "layer2", "layer3"
            layer_num = int(args.layer_strategy.replace("layer", ""))

        layer_counts[layer_num] += 1

        print(f"\n{'='*70}")
        print(f"[{i}/{len(bp_cases)}] Cluster {bp_case.cluster_id} — {bp_case.intent[:50]}...")
        print(f"{'='*70}")
        print(f"  UserChat ID: {bp_case.user_chat_id}")
        print(f"  UserChat URL: {bp_case.user_chat_url}")
        print(f"  Category: {bp_case.category_display}")
        print(f"  Cluster size: {bp_case.cluster_size}")
        print(f"  Selected Layer: {layer_num}")

        initial_msg, transcript = await generate_and_test_bp_case(
            bp_case=bp_case,
            layer_num=layer_num,
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
                "bp_url": bp_case.user_chat_url,
                "bp_user_chat_id": bp_case.user_chat_id,
                "bp_intent": bp_case.intent,
                "bp_cluster_id": bp_case.cluster_id,
                "bp_cluster_category": bp_case.category_display,
                "bp_cluster_size": bp_case.cluster_size,
                "layer": layer_num,
                "initial_message": initial_msg,
                "transcript": transcript,
            })
        else:
            print(f"    → Failed")

        # Delay between tests
        await asyncio.sleep(2)

    # Step 4: Save results
    print(f"\n{'='*70}")
    print(f"Step 4: Save results")
    print(f"{'='*70}")

    from dataclasses import asdict

    output_path = output_dir / "transcripts.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            record = {
                "bp_url": r["bp_url"],
                "bp_user_chat_id": r["bp_user_chat_id"],
                "bp_intent": r["bp_intent"],
                "bp_cluster_id": r["bp_cluster_id"],
                "bp_cluster_category": r["bp_cluster_category"],
                "bp_cluster_size": r["bp_cluster_size"],
                "layer": r["layer"],
                "initial_message": r["initial_message"],
                "transcript": asdict(r["transcript"]),
            }
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")

    print(f"\n{'='*70}")
    print(f"Summary")
    print(f"{'='*70}")
    print(f"Total tested: {len(results)}/{len(bp_cases)}")
    print(f"Success rate: {len(results)/len(bp_cases)*100:.1f}%")
    print(f"Layer distribution:")
    print(f"  Layer 1: {layer_counts[1]}")
    print(f"  Layer 2: {layer_counts[2]}")
    print(f"  Layer 3: {layer_counts[3]}")
    print(f"\n✅ Transcripts saved to: {output_path}")
    print()

    # Generate QA reports automatically
    print("📊 Generating QA reports...")
    try:
        # Extract client name from clustered_excel path
        # e.g., ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx -> 차란
        excel_path = Path(clustered_excel)
        client_name = excel_path.parent.parent.name if excel_path.parent.parent.name != "results" else "Client"

        html_path, md_path = generate_bp_qa_reports(
            transcripts_path=output_path,
            output_dir=output_dir,
            client_name=client_name
        )
        print(f"✅ HTML 리포트 생성: {html_path}")
        print(f"✅ Markdown 리포트 생성: {md_path}")
    except Exception as e:
        print(f"⚠️ 리포트 생성 실패: {e}")
        print("   수동으로 생성하려면:")
        print(f"     python3 -m tools.bp_qa_report_generator \\")
        print(f"       {output_path} \\")
        print(f"       {output_dir} \\")
        print(f"       <client_name>")
    print()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Run Best Practice QA from sop-agent clustering results"
    )
    parser.add_argument(
        "--clustered-excel",
        required=True,
        help="Path to *_clustered.xlsx from sop-agent Stage 1",
    )
    parser.add_argument(
        "--channel-url",
        required=True,
        help="Channel.io test channel URL",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for results",
    )
    parser.add_argument(
        "--manual-bp",
        help="Path to manual Best Practice file (TSV/CSV/Excel with user_chat_id or url column). "
             "If provided, uses manual selection instead of automatic extraction.",
    )
    parser.add_argument(
        "--target-total",
        type=int,
        default=100,
        help="Target number of Best Practice cases to extract (default: 100, ignored if --manual-bp)",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=10,
        help="Minimum cluster size to consider (default: 10, ignored if --manual-bp)",
    )
    parser.add_argument(
        "--max-per-cluster",
        type=int,
        default=10,
        help="Maximum cases per cluster (default: 10, ignored if --manual-bp)",
    )
    parser.add_argument(
        "--layer-strategy",
        choices=["random", "balanced", "layer1", "layer2", "layer3"],
        default="random",
        help="Layer selection strategy (default: random)",
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
        help="ALF reply timeout in seconds (default: 120.0)",
    )

    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
