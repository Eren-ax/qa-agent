#!/usr/bin/env python3
"""Test HTML report generation with sample data.

Usage:
    uv run python scripts/test_html_report.py
"""

from pathlib import Path

from tools.report_html_generator import generate_html_report
from tools.result_store import AlfMessageRecord, Transcript, Turn

# Sample data
sample_transcript = Transcript(
    schema_version="v0",
    run_id="test-run-001",
    scenario_id="product_001",
    started_at="2026-04-17T10:00:00Z",
    ended_at="2026-04-17T10:05:00Z",
    terminated_reason="completed",
    turns=[
        Turn(
            turn_index=0,
            user_message="랜더플라이트 자켓 사이즈 추천 부탁드려요! 170cm 62kg입니다.",
            user_ts=1776339841.880262,
            alf_messages=[
                AlfMessageRecord(
                    node_id="node-001",
                    text="안녕하세요, 벨리에입니다!",
                    ts=1776339853.028095,
                ),
                AlfMessageRecord(
                    node_id="node-002",
                    text="말씀해주신 170cm / 62kg 체형 기준으로는 랜더플라이트 자켓 01(95) 사이즈를 권장드립니다.",
                    ts=1776339853.045165,
                ),
            ],
            reply_latency_s=11.2,
        ),
        Turn(
            turn_index=1,
            user_message="감사해요! 근데 01(95) 사이즈가 딱 맞는 건지, 아니면 약간 여유 있게 입는 스타일인지 궁금해서요.",
            user_ts=1776339858.184291,
            alf_messages=[
                AlfMessageRecord(
                    node_id="node-003",
                    text="170cm / 62kg 기준으로\n- 01(95)는 기본 정핏~살짝 여유 있는 느낌\n- 슬림/적당핏 선호 → 01(95)\n- 더 루즈하게 입고 싶으시면 → 02(100)도 고려 가능",
                    ts=1776339867.996879,
                ),
            ],
            reply_latency_s=9.8,
        ),
    ],
)

sample_run_score = {
    "aggregate": {
        "coverage": 0.7180,
        "engagement_rate": 0.7180,
        "resolution_rate": 1.0,
        "by_phase": {
            "_phase1_summary": {
                "coverage": 0.7180,
                "engagement_rate": 0.7180,
                "resolution_rate": 1.0,
            },
            "_phase2_summary": {
                "coverage": 0.8615,
                "engagement_rate": 0.8615,
                "resolution_rate": 1.0,
            },
        },
    }
}

sample_scenario_metadata = {
    "product_001": {
        "intent": "제품정보/사이즈 추천",
        "weight": 0.277,
    }
}


def main():
    """Generate a test HTML report."""
    html = generate_html_report(
        run_id="test-run-001",
        client_name="테스트 고객사",
        run_score=sample_run_score,
        transcripts=[sample_transcript],
        scenario_metadata=sample_scenario_metadata,
    )

    # Write to test output
    output_path = Path("storage/test_report.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"✓ Test HTML report written to {output_path}")
    print(f"  Open with: open {output_path}")


if __name__ == "__main__":
    main()
