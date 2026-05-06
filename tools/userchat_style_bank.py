"""Build a style reference bank from clustered userchat messages.

Extracts real customer utterances grouped by cluster to serve as
few-shot style examples during QA scenario generation (Layer 1 strategy).

Usage:
    from tools.userchat_style_bank import build_style_bank

    bank = build_style_bank(
        messages_csv="~/Desktop/ax-task/차란/01_clustering/차란_messages.csv",
        cluster_tags_xlsx="~/Desktop/ax-task/차란/01_clustering/차란_tags.xlsx",
        top_k=5
    )

    # bank structure:
    # {
    #   "cluster_id_0": {
    #       "label": "초기 문의, 미분류 문의, 상담원 연결 분기",
    #       "utterances": ["실제 고객 발화 1", "실제 고객 발화 2", ...]
    #   },
    #   ...
    # }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None


def build_style_bank(
    messages_csv: str | Path,
    cluster_tags_xlsx: str | Path,
    top_k: int = 5,
    min_length: int = 10,
    max_length: int = 200,
) -> dict[str, dict[str, Any]]:
    """Build a style reference bank from clustered userchat data.

    Args:
        messages_csv: Path to messages CSV with cluster_id column
        cluster_tags_xlsx: Path to cluster tags Excel with cluster_id and label
        top_k: Number of representative utterances per cluster
        min_length: Minimum character length for valid utterances
        max_length: Maximum character length for valid utterances

    Returns:
        Dict mapping cluster_id to {label, utterances}
    """
    if pd is None:
        raise ImportError("pandas required: pip install pandas openpyxl")

    messages_csv = Path(messages_csv).expanduser()
    cluster_tags_xlsx = Path(cluster_tags_xlsx).expanduser()

    if not messages_csv.exists():
        raise FileNotFoundError(f"Messages CSV not found: {messages_csv}")
    if not cluster_tags_xlsx.exists():
        raise FileNotFoundError(f"Cluster tags not found: {cluster_tags_xlsx}")

    # Load cluster tags
    tags_df = pd.read_excel(cluster_tags_xlsx)
    cluster_labels = {}
    for _, row in tags_df.iterrows():
        cluster_id = str(row.get("cluster_id", row.get("Cluster ID", "")))
        label = row.get("label", row.get("Label", row.get("태그", "")))
        if cluster_id and label:
            cluster_labels[cluster_id] = label

    # Load messages
    msg_df = pd.read_csv(messages_csv)

    # Filter: only user messages
    user_df = msg_df[msg_df["personType"] == "user"].copy()

    # Extract utterances per cluster
    bank = {}

    for cluster_id in user_df["cluster_id"].unique():
        cluster_id_str = str(cluster_id)

        # Get label from tags
        label = cluster_labels.get(cluster_id_str, f"Cluster {cluster_id}")

        # Filter messages for this cluster
        cluster_msgs = user_df[user_df["cluster_id"] == cluster_id]["plainText"].dropna()

        # Clean and filter
        cleaned = []
        for msg in cluster_msgs:
            msg = clean_utterance(str(msg))
            if min_length <= len(msg) <= max_length:
                cleaned.append(msg)

        # Deduplicate
        unique = list(dict.fromkeys(cleaned))  # preserves order

        # Select top_k diverse utterances
        selected = select_diverse_utterances(unique, top_k)

        if selected:
            bank[cluster_id_str] = {
                "label": label,
                "utterances": selected,
            }

    return bank


def clean_utterance(text: str) -> str:
    """Clean user utterance for use as style reference.

    - Remove URLs
    - Remove excessive whitespace
    - Preserve natural spacing and punctuation
    """
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text


def select_diverse_utterances(utterances: list[str], top_k: int) -> list[str]:
    """Select diverse utterances to represent cluster style.

    Strategy:
    - Prefer medium-length messages (not too short, not too long)
    - Avoid duplicate sentence structures
    - Prioritize messages with natural markers (이모티콘, 구어체 등)
    """
    if len(utterances) <= top_k:
        return utterances

    # Score each utterance
    scored = []
    for utt in utterances:
        score = 0

        # Prefer medium length
        length_score = min(len(utt), 100) / 100.0  # normalize to [0, 1]
        score += length_score * 2

        # Bonus for natural markers
        if any(emoji in utt for emoji in ["ㅠ", "ㅜ", "ㅎ", "!", "?"]):
            score += 1

        # Bonus for conversational endings
        if any(utt.endswith(end) for end in ["요", "요.", "요?", "요!", "인데", "인데요", "네요"]):
            score += 1

        scored.append((score, utt))

    # Sort by score descending, then take top_k
    scored.sort(key=lambda x: x[0], reverse=True)

    return [utt for _, utt in scored[:top_k]]


def get_style_references_for_intent(
    bank: dict[str, dict[str, Any]],
    intent_label: str,
    top_k: int = 3,
) -> list[str]:
    """Get style reference utterances for a specific intent.

    Args:
        bank: Style bank from build_style_bank()
        intent_label: Intent label (e.g. "차란백 배송, 추가 요청, 분실 및 취소")
        top_k: Number of utterances to return

    Returns:
        List of style reference utterances
    """
    # Find matching cluster
    for cluster_id, data in bank.items():
        if data["label"] == intent_label:
            return data["utterances"][:top_k]

    # Fallback: fuzzy match
    for cluster_id, data in bank.items():
        # Check if any keyword from intent_label appears in cluster label
        intent_keywords = intent_label.replace(",", " ").replace("및", " ").split()
        cluster_keywords = data["label"].replace(",", " ").replace("및", " ").split()

        overlap = set(intent_keywords) & set(cluster_keywords)
        if overlap:
            return data["utterances"][:top_k]

    # No match: return empty
    return []


def format_style_references_for_prompt(
    utterances: list[str],
    prefix: str = "실제 고객 발화 예시",
) -> str:
    """Format style references as a prompt section.

    Args:
        utterances: List of utterances
        prefix: Section title

    Returns:
        Formatted markdown section
    """
    if not utterances:
        return ""

    lines = [f"### {prefix}\n"]
    for i, utt in enumerate(utterances, 1):
        lines.append(f"{i}. \"{utt}\"")

    lines.append("\n**중요**: 위 발화들의 말투, 문장 구조, 감정 표현 방식을 그대로 따라하세요.")
    lines.append("- 어휘 선택 (예: \"가능한가요\" vs \"되나요\" vs \"해주세요\")")
    lines.append("- 문장 길이와 끊김")
    lines.append("- 이모티콘/강조 사용 패턴")
    lines.append("- 감정 온도\n")

    return "\n".join(lines)
