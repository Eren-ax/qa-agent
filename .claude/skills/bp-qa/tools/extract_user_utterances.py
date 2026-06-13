"""Extract real user utterances from consultation data Excel files.

Reads raw consultation data (xlsx) and extracts actual customer messages
to be used as source_phrases for realistic QA persona generation.

Usage:
    from tools.extract_user_utterances import extract_utterances_from_xlsx

    utterances = extract_utterances_from_xlsx(
        xlsx_path="~/sop-agent/data/consultations.xlsx",
        intent_keywords=["환불", "반품"],
        max_samples=10
    )
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None


def extract_utterances_from_xlsx(
    xlsx_path: str | Path,
    intent_keywords: list[str] | None = None,
    max_samples: int = 10,
    min_length: int = 5,
    max_length: int = 150,
) -> list[str]:
    """Extract real user utterances from consultation Excel data.

    Args:
        xlsx_path: Path to consultation data Excel file
        intent_keywords: Filter for specific intent (e.g. ["환불", "반품"])
        max_samples: Maximum number of utterances to return
        min_length: Minimum character length for valid utterances
        max_length: Maximum character length for valid utterances

    Returns:
        List of cleaned user utterances
    """
    if pd is None:
        raise ImportError("pandas required for xlsx reading: pip install pandas openpyxl")

    xlsx_path = Path(xlsx_path).expanduser()
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Consultation data not found: {xlsx_path}")

    # Read Excel file
    df = pd.read_excel(xlsx_path)

    # Common column name variations for user messages
    user_msg_cols = [
        "user_message", "customer_message", "message", "content",
        "유저메시지", "고객메시지", "메시지", "내용",
        "첫 메시지", "first_message", "initial_message"
    ]

    # Find the actual column name
    msg_col = None
    for col in user_msg_cols:
        if col in df.columns:
            msg_col = col
            break

    if msg_col is None:
        # Try case-insensitive match
        lower_cols = {c.lower(): c for c in df.columns}
        for col in user_msg_cols:
            if col.lower() in lower_cols:
                msg_col = lower_cols[col.lower()]
                break

    if msg_col is None:
        raise ValueError(
            f"Could not find user message column. Available columns: {list(df.columns)}"
        )

    # Extract messages
    messages = df[msg_col].dropna().astype(str).tolist()

    # Filter by intent keywords if provided
    if intent_keywords:
        filtered = []
        for msg in messages:
            if any(kw in msg for kw in intent_keywords):
                filtered.append(msg)
        messages = filtered

    # Clean and filter messages
    cleaned = []
    for msg in messages:
        msg = clean_utterance(msg)
        if min_length <= len(msg) <= max_length:
            cleaned.append(msg)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for msg in cleaned:
        if msg not in seen:
            seen.add(msg)
            unique.append(msg)

    # Return up to max_samples
    return unique[:max_samples]


def clean_utterance(text: str) -> str:
    """Clean user utterance for use in QA scenarios.

    - Remove system metadata (timestamps, user IDs, etc.)
    - Remove excessive whitespace
    - Preserve natural Korean spacing
    """
    # Remove common metadata patterns
    text = re.sub(r'\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]', '', text)  # [2024-01-01 12:00:00]
    text = re.sub(r'<@U[A-Z0-9]+>', '', text)  # Slack user IDs
    text = re.sub(r'https?://\S+', '', text)  # URLs (keep actual content)

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text


def extract_utterances_by_intent(
    xlsx_path: str | Path,
    intent_map: dict[str, list[str]],
    max_per_intent: int = 10,
) -> dict[str, list[str]]:
    """Extract utterances grouped by intent.

    Args:
        xlsx_path: Path to consultation data Excel file
        intent_map: Mapping from intent label to keywords
            e.g. {"환불 문의": ["환불", "반품"], "배송 조회": ["배송", "추적"]}
        max_per_intent: Max utterances per intent

    Returns:
        Dict mapping intent label to list of utterances
    """
    result = {}

    for intent, keywords in intent_map.items():
        utterances = extract_utterances_from_xlsx(
            xlsx_path=xlsx_path,
            intent_keywords=keywords,
            max_samples=max_per_intent,
        )
        result[intent] = utterances

    return result


def load_utterances_from_patterns_json(
    patterns_json_path: str | Path,
    max_per_pattern: int = 5,
) -> dict[str, list[str]]:
    """Load common_phrases from sop-agent patterns.json.

    This is the primary source for utterances (doesn't require raw xlsx).

    Args:
        patterns_json_path: Path to sop-agent patterns.json
        max_per_pattern: Max phrases per pattern

    Returns:
        Dict mapping pattern name to list of common phrases
    """
    import json

    patterns_path = Path(patterns_json_path).expanduser()
    if not patterns_path.exists():
        raise FileNotFoundError(f"patterns.json not found: {patterns_path}")

    with open(patterns_path, encoding="utf-8") as f:
        data = json.load(f)

    result = {}

    # Extract from clusters
    if "clusters" in data:
        for cluster in data["clusters"]:
            cluster_label = cluster.get("label", "unknown")

            # Get patterns from this cluster
            for pattern in cluster.get("patterns", []):
                pattern_name = pattern.get("name", "unknown")
                common_phrases = pattern.get("common_phrases", [])

                if common_phrases:
                    key = f"{cluster_label}/{pattern_name}"
                    result[key] = common_phrases[:max_per_pattern]

    # Fallback: if no clusters, try top-level patterns
    elif "patterns" in data:
        for pattern in data["patterns"]:
            pattern_name = pattern.get("name", "unknown")
            common_phrases = pattern.get("common_phrases", [])

            if common_phrases:
                result[pattern_name] = common_phrases[:max_per_pattern]

    return result
