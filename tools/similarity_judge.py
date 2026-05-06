"""Similarity judge: compare original vs replayed ALF responses.

Scores how similar the replayed ALF responses are to the original conversation.

Metrics:
1. Semantic similarity (embedding-based cosine similarity)
2. Structural similarity (length ratio, presence of links/formatting)
3. Overall similarity score (weighted average)

Usage:
    uv run python -m tools.similarity_judge \
        --original /tmp/extracted_userchat.json \
        --replay /tmp/replay_result.json \
        --output /tmp/similarity_scores.json
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from tools.llm_client import create_llm_client, call_llm, ProviderType


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://prism.ch.dev")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "anthropic/claude-sonnet-4-6")


@dataclass
class TurnSimilarity:
    """Similarity score for one turn."""

    turn: int
    semantic_score: float  # 0.0-1.0
    structural_score: float  # 0.0-1.0
    overall_score: float  # 0.0-1.0
    notes: str = ""


@dataclass
class SimilarityReport:
    """Complete similarity analysis."""

    original_user_chat_id: str
    turn_scores: list[TurnSimilarity]
    avg_semantic: float
    avg_structural: float
    avg_overall: float
    notes: str = ""

    def to_json(self) -> dict:
        """Export to JSON."""
        return {
            'originalUserChatId': self.original_user_chat_id,
            'turnScores': [
                {
                    'turn': t.turn,
                    'semanticScore': t.semantic_score,
                    'structuralScore': t.structural_score,
                    'overallScore': t.overall_score,
                    'notes': t.notes
                }
                for t in self.turn_scores
            ],
            'avgSemantic': self.avg_semantic,
            'avgStructural': self.avg_structural,
            'avgOverall': self.avg_overall,
            'notes': self.notes
        }


def compute_structural_similarity(original: str, replay: str) -> float:
    """Compute structural similarity (length, formatting).

    Returns:
        Score 0.0-1.0 based on:
        - Length ratio (how close are the lengths)
        - Presence of URLs
        - Markdown formatting
    """
    if not original or not replay:
        return 0.0

    # Length ratio (1.0 if same length, decreases as ratio differs)
    len_original = len(original)
    len_replay = len(replay)
    len_ratio = min(len_original, len_replay) / max(len_original, len_replay)

    # URL presence (1.0 if both have or both don't have URLs)
    has_url_original = 'http' in original
    has_url_replay = 'http' in replay
    url_score = 1.0 if has_url_original == has_url_replay else 0.5

    # Markdown formatting (bullet points, bold, etc.)
    has_bullet_original = '*' in original or '-' in original
    has_bullet_replay = '*' in replay or '-' in replay
    format_score = 1.0 if has_bullet_original == has_bullet_replay else 0.7

    # Weighted average
    return 0.5 * len_ratio + 0.3 * url_score + 0.2 * format_score


async def compute_semantic_similarity(
    original: str,
    replay: str,
    client,
    provider: ProviderType,
    model: str
) -> tuple[float, str]:
    """Compute semantic similarity using LLM judgment.

    Returns:
        (score 0.0-1.0, explanation)
    """
    if not original or not replay:
        return 0.0, "Empty response"

    system_prompt = """You are a similarity judge for ALF responses.

Your task: compare two ALF responses to the same user question and rate their semantic similarity.

Semantic similarity means:
- Same core information/answer
- Same intent (e.g., both provide pricing, both escalate, etc.)
- Similar tone (formal, friendly, etc.)

Differences in exact wording or formatting are OK if the meaning is the same.

Output format:
{
  "score": 0.85,
  "reasoning": "Both responses provide the same pricing information and recommend consultation. Minor wording differences but semantically equivalent."
}

Score scale:
- 1.0: Semantically identical (same info, same intent)
- 0.7-0.9: Very similar (same core info, minor differences)
- 0.4-0.6: Somewhat similar (overlapping info but some differences)
- 0.1-0.3: Different (different info or intent)
- 0.0: Completely different
"""

    user_prompt = f"""Compare these two ALF responses:

[Original Response]
{original}

[Replay Response]
{replay}

Rate their semantic similarity (0.0-1.0) and explain why."""

    response = await call_llm(
        client=client,
        provider=provider,
        model=model,
        system=system_prompt,
        user=user_prompt,
        max_tokens=500,
        temperature=0.0
    )

    # Parse JSON response
    try:
        data = json.loads(response)
        score = float(data.get('score', 0.0))
        reasoning = data.get('reasoning', '')
        return score, reasoning
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        return 0.5, f"Parse error: {e}"


async def judge_similarity(
    original_json_path: Path,
    replay_json_path: Path
) -> SimilarityReport:
    """Judge similarity between original and replayed conversations.

    Args:
        original_json_path: Path to extracted user-chat JSON
        replay_json_path: Path to replay result JSON

    Returns:
        SimilarityReport with per-turn and aggregate scores
    """
    # Load data
    with open(original_json_path) as f:
        original_data = json.load(f)

    with open(replay_json_path) as f:
        replay_data = json.load(f)

    # Create LLM client for semantic similarity
    client, model, provider_type = create_llm_client()

    turn_scores: list[TurnSimilarity] = []

    print("\n=== Similarity Judgment ===\n")

    # Match turns by turn number
    original_turns = {t['turn']: t for t in original_data['turns']}
    replay_turns = {t['turn']: t for t in replay_data['replayTurns']}

    common_turns = set(original_turns.keys()) & set(replay_turns.keys())

    for turn_num in sorted(common_turns):
        original_turn = original_turns[turn_num]
        replay_turn = replay_turns[turn_num]

        original_alf = original_turn['alf']
        replay_alf = ' '.join(replay_turn['alfMessages'])  # concatenate multiple messages

        print(f"[Turn {turn_num}]")
        print(f"  Original: {original_alf[:100]}...")
        print(f"  Replay:   {replay_alf[:100]}...")

        # Structural similarity (fast, rule-based)
        structural = compute_structural_similarity(original_alf, replay_alf)

        # Semantic similarity (LLM-based, slower)
        semantic, reasoning = await compute_semantic_similarity(
            original_alf, replay_alf, client, provider_type, JUDGE_MODEL
        )

        # Overall score (weighted average)
        overall = 0.7 * semantic + 0.3 * structural

        print(f"  Structural: {structural:.2f}")
        print(f"  Semantic:   {semantic:.2f} — {reasoning[:80]}...")
        print(f"  Overall:    {overall:.2f}\n")

        turn_scores.append(TurnSimilarity(
            turn=turn_num,
            semantic_score=semantic,
            structural_score=structural,
            overall_score=overall,
            notes=reasoning
        ))

    # Aggregate scores
    avg_semantic = sum(t.semantic_score for t in turn_scores) / len(turn_scores) if turn_scores else 0.0
    avg_structural = sum(t.structural_score for t in turn_scores) / len(turn_scores) if turn_scores else 0.0
    avg_overall = sum(t.overall_score for t in turn_scores) / len(turn_scores) if turn_scores else 0.0

    return SimilarityReport(
        original_user_chat_id=original_data['userChatId'],
        turn_scores=turn_scores,
        avg_semantic=avg_semantic,
        avg_structural=avg_structural,
        avg_overall=avg_overall,
        notes=f"Judged {len(turn_scores)} turns"
    )


async def main():
    parser = argparse.ArgumentParser(
        description='Judge similarity between original and replayed conversations'
    )
    parser.add_argument(
        '--original',
        required=True,
        help='Path to extracted user-chat JSON'
    )
    parser.add_argument(
        '--replay',
        required=True,
        help='Path to replay result JSON'
    )
    parser.add_argument(
        '--output',
        help='Output JSON path (default: print to stdout)'
    )

    args = parser.parse_args()

    # Judge similarity
    report = await judge_similarity(
        Path(args.original),
        Path(args.replay)
    )

    # Output
    output_json = json.dumps(report.to_json(), ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output_json, encoding='utf-8')
        print(f"\n✅ Similarity report saved to {args.output}")
    else:
        print("\n=== Similarity Report ===")
        print(output_json)

    # Summary
    print(f"\n📊 Summary:")
    print(f"  Average Semantic:    {report.avg_semantic:.2f}")
    print(f"  Average Structural:  {report.avg_structural:.2f}")
    print(f"  Average Overall:     {report.avg_overall:.2f}")


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
