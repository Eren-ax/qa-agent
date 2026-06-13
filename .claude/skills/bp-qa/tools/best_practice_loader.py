"""Load best practice user chats from Excel and convert to QA scenarios.

Reads '차란 - Best Practice.xlsx' and extracts high-quality customer interactions
for scenario generation.

Usage:
    from tools.best_practice_loader import load_best_practices

    scenarios = load_best_practices(
        excel_path="~/Downloads/차란 - Best Practice.xlsx",
        priority_only=True,  # ⭐ only
        rag_only=True,       # 🟢 RAG only
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None


@dataclass
class BestPracticeRecord:
    """One best practice user chat record."""

    priority: str  # "⭐" or empty
    category: str  # "유형 4 — 검수·상품화"
    subcategory: str  # "검수일정"
    classification: str  # "🟢 RAG", "🔴 어드민 의존", etc.
    reason: str  # 베스트 사유
    url: str  # UserChat URL
    intent: str  # 고객 의도
    responder: str  # 로봇 단독, 로봇→상담원, 상담원 단독
    bot_response: str  # 봇 응대
    agent_response: Optional[str]  # 상담원 응대 (if any)

    @property
    def user_chat_id(self) -> str | None:
        """Extract UserChat ID from URL.

        Example:
            https://desk.channel.io/charan/user-chats/69e6e6d69f3e263c3ac0
            → 69e6e6d69f3e263c3ac0
        """
        match = re.search(r'/user-chats/([a-f0-9]+)', self.url)
        return match.group(1) if match else None

    @property
    def is_priority(self) -> bool:
        """Check if this is priority (⭐) case."""
        return self.priority == "⭐"

    @property
    def is_rag_only(self) -> bool:
        """Check if this is RAG-only (no admin dependency)."""
        return self.classification.startswith("🟢 RAG")

    @property
    def is_bot_only(self) -> bool:
        """Check if bot handled this alone."""
        return self.responder == "로봇 단독"


def load_best_practices(
    excel_path: str | Path,
    priority_only: bool = False,
    rag_only: bool = False,
    bot_only: bool = False,
) -> list[BestPracticeRecord]:
    """Load best practice records from Excel.

    Args:
        excel_path: Path to '차란 - Best Practice.xlsx'
        priority_only: If True, only return ⭐ priority cases
        rag_only: If True, only return 🟢 RAG cases (no admin dependency)
        bot_only: If True, only return cases handled by bot alone

    Returns:
        List of BestPracticeRecord
    """
    if pd is None:
        raise ImportError("pandas is required. Install with: pip install pandas openpyxl")

    excel_path = Path(excel_path).expanduser()
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    df = pd.read_excel(excel_path)

    records = []
    for _, row in df.iterrows():
        # Skip rows with missing URL
        if pd.isna(row['링크']) or not row['링크']:
            continue

        record = BestPracticeRecord(
            priority=str(row['우선순위']) if not pd.isna(row['우선순위']) else "",
            category=str(row['유형']) if not pd.isna(row['유형']) else "",
            subcategory=str(row['세부유형']) if not pd.isna(row['세부유형']) else "",
            classification=str(row['분류']) if not pd.isna(row['분류']) else "",
            reason=str(row['베스트 사유']) if not pd.isna(row['베스트 사유']) else "",
            url=str(row['링크']),
            intent=str(row['고객 의도']) if not pd.isna(row['고객 의도']) else "",
            responder=str(row['답변자']) if not pd.isna(row['답변자']) else "",
            bot_response=str(row['봇 응대']) if not pd.isna(row['봇 응대']) else "",
            agent_response=str(row['상담원 응대']) if not pd.isna(row['상담원 응대']) else None,
        )

        # Apply filters
        if priority_only and not record.is_priority:
            continue
        if rag_only and not record.is_rag_only:
            continue
        if bot_only and not record.is_bot_only:
            continue

        records.append(record)

    return records


def extract_initial_message(url: str) -> str:
    """Extract first user message from UserChat URL.

    TODO: Implement using trace-alf-userchat skill or Langfuse MCP
    For now, returns placeholder.
    """
    # This will be implemented later
    return f"[TODO: Extract from {url}]"


if __name__ == "__main__":
    # Test
    records = load_best_practices(
        "~/Downloads/차란 - Best Practice.xlsx",
        priority_only=True,
        rag_only=True,
    )

    print(f"Loaded {len(records)} best practice records")
    print()

    if records:
        print("Sample record:")
        r = records[0]
        print(f"  URL: {r.url}")
        print(f"  UserChat ID: {r.user_chat_id}")
        print(f"  Intent: {r.intent}")
        print(f"  Classification: {r.classification}")
        print(f"  Responder: {r.responder}")
