"""Generate 10 scenarios each using Layer 1, 2, 3 for side-by-side comparison.

User will manually review and distinguish which is most human-like.
"""

from pathlib import Path
import json
import random
from anthropic import Anthropic
import os
from dotenv import load_dotenv

# Load .env
load_dotenv(Path("~/qa-agent/.env").expanduser())

# Load style bank
STYLE_BANK_PATH = Path("~/qa-agent/storage/charan_style_bank.json").expanduser()

with open(STYLE_BANK_PATH, encoding="utf-8") as f:
    STYLE_BANK = json.load(f)

# Initialize Anthropic client (Prism Gateway)
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://prism.ch.dev"
)

# Select 10 diverse clusters
def select_test_clusters(bank: dict, n: int = 10) -> list[tuple[str, dict]]:
    """Select diverse clusters for testing."""
    clusters = list(bank.items())
    random.seed(42)  # Fixed seed for reproducibility
    return random.sample(clusters, min(n, len(clusters)))

SELECTED_CLUSTERS = select_test_clusters(STYLE_BANK, 10)


# Layer 1: Style Reference Injection
def generate_layer1(intent: str, style_refs: list[str]) -> str:
    """Generate with style references."""
    prompt = f"""You are generating a QA scenario initial message.

### 실제 고객 발화 예시 (스타일 참고용)

{chr(10).join(f'{i}. "{ref}"' for i, ref in enumerate(style_refs[:3], 1))}

**중요**: 위 발화들의 말투, 문장 구조, 감정 표현 방식을 그대로 따라하세요.
- 어휘 선택 (예: "가능한가요" vs "되나요" vs "해주세요")
- 문장 길이와 끊김
- 이모티콘/강조 사용 패턴 (ㅠㅠ, !, ? 등)
- 감정 온도
- "안녕하세요" 같은 인사말 제거 (실제 고객은 바로 본론)
- 짧게 (50~100자 권장)

---

[생성할 시나리오]
Intent: {intent}

위 실제 대화의 "말하는 방식"을 그대로 따라하되, 내용은 intent에 맞게 작성하세요.

Output ONLY the customer message, nothing else."""

    response = client.messages.create(
        model="anthropic/claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


# Layer 2: Utterance Transplant
def generate_layer2(utterances: list[str]) -> str:
    """Select real utterance (shortest for directness)."""
    return min(utterances, key=len)


# Layer 3: Layer 1 + Validation
def validate_style(candidate: str, style_refs: list[str]) -> float:
    """Simple style similarity check."""
    score = 0.0

    # Check 1: Length similarity
    avg_len = sum(len(ref) for ref in style_refs) / len(style_refs)
    if abs(len(candidate) - avg_len) < avg_len * 0.3:
        score += 0.3

    # Check 2: Ending pattern
    common_endings = ["요", "요?", "나요", "나요?", "인가요", "인가요?", "ㅠㅠ", "ㅜㅜ"]
    if any(candidate.endswith(end) for end in common_endings):
        score += 0.3

    # Check 3: No formal patterns
    formal_patterns = ["습니다", "드립니다", "겠습니다"]
    if not any(pattern in candidate for pattern in formal_patterns):
        score += 0.2

    # Check 4: Casual particles
    casual_particles = ["근데", "그럼", "혹시", "아직"]
    if any(particle in candidate for particle in casual_particles):
        score += 0.2

    return min(score, 1.0)


def generate_layer3(intent: str, style_refs: list[str], max_retry: int = 2) -> str:
    """Layer 1 + validation loop."""
    for attempt in range(max_retry):
        candidate = generate_layer1(intent, style_refs)
        score = validate_style(candidate, style_refs)

        if score >= 0.7:
            return candidate

    return candidate  # Return last attempt


def main():
    print("=" * 100)
    print("Layer 1 vs Layer 2 vs Layer 3 - 10개 시나리오 비교")
    print("=" * 100)
    print(f"\n선택된 클러스터: {len(SELECTED_CLUSTERS)}개")
    print("각 Layer별 10개씩 생성 (총 30개)\n")

    results = []

    for i, (cluster_id, cluster_data) in enumerate(SELECTED_CLUSTERS, 1):
        intent = cluster_data["label"]
        utterances = cluster_data["utterances"]

        print(f"[{i}/10] Intent: {intent[:50]}...")

        # Generate with all 3 layers
        print("  - Layer 1 생성 중...", end=" ")
        layer1_msg = generate_layer1(intent, utterances)
        print("✓")

        print("  - Layer 2 생성 중...", end=" ")
        layer2_msg = generate_layer2(utterances)
        print("✓")

        print("  - Layer 3 생성 중...", end=" ")
        layer3_msg = generate_layer3(intent, utterances)
        print("✓")

        results.append({
            "id": i,
            "intent": intent,
            "cluster_id": cluster_id,
            "style_refs": utterances[:3],
            "layer1": layer1_msg,
            "layer2": layer2_msg,
            "layer3": layer3_msg,
        })

        print()

    # Save results
    output_path = Path("~/qa-agent/storage/all_layers_comparison.json").expanduser()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ Results saved to: {output_path}")

    # Generate HTML comparison table
    generate_html_table(results)


def generate_html_table(results: list[dict]):
    """Generate HTML table for easy visual comparison."""

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Layer 1 vs 2 vs 3 비교</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        h1 {
            text-align: center;
            color: #333;
        }
        .instructions {
            background: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }
        .instructions h2 {
            margin-top: 0;
            color: #856404;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 40px;
        }
        th {
            background: #343a40;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 15px;
            border-bottom: 1px solid #dee2e6;
            vertical-align: top;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .intent {
            font-weight: 600;
            color: #495057;
            margin-bottom: 10px;
        }
        .message {
            padding: 12px;
            border-radius: 6px;
            margin: 8px 0;
            line-height: 1.6;
        }
        .layer1 { background: #e3f2fd; border-left: 4px solid #2196F3; }
        .layer2 { background: #e8f5e9; border-left: 4px solid #4CAF50; }
        .layer3 { background: #fff3e0; border-left: 4px solid #FF9800; }
        .layer-label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: #6c757d;
            margin-bottom: 6px;
        }
        .meta {
            font-size: 12px;
            color: #6c757d;
            margin-top: 8px;
        }
        .style-refs {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            font-size: 13px;
            color: #495057;
            margin-top: 8px;
        }
        .style-refs strong {
            display: block;
            margin-bottom: 4px;
            color: #343a40;
        }
    </style>
</head>
<body>
    <h1>🔍 Layer 1 vs Layer 2 vs Layer 3 시나리오 비교</h1>

    <div class="instructions">
        <h2>📋 비교 방법</h2>
        <p><strong>목표:</strong> 어떤 Layer가 가장 "실제 고객처럼" 들리는지 육안으로 판단</p>

        <p><strong>평가 기준:</strong></p>
        <ul>
            <li><strong>자연스러움:</strong> AI가 만든 것처럼 들리지 않는가?</li>
            <li><strong>구어체:</strong> "~요", "~인가요", "~인데" 같은 자연스러운 어미 사용</li>
            <li><strong>직접성:</strong> 불필요한 인사말 없이 바로 본론</li>
            <li><strong>감정 표현:</strong> 불편함, 긴급함, 궁금함이 자연스럽게 드러나는가?</li>
        </ul>

        <p><strong>Layer 설명:</strong></p>
        <ul>
            <li><strong style="color: #2196F3;">Layer 1 (파란색):</strong> LLM에게 실제 발화 3개 예시 보여주고 스타일 따라하라고 지시</li>
            <li><strong style="color: #4CAF50;">Layer 2 (초록색):</strong> 실제 고객 발화 그대로 재사용 (LLM 사용 안 함)</li>
            <li><strong style="color: #FF9800;">Layer 3 (주황색):</strong> Layer 1 + 검증 루프 (품질 낮으면 재생성)</li>
        </ul>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 5%">#</th>
                <th style="width: 20%">Intent</th>
                <th style="width: 75%">생성 결과</th>
            </tr>
        </thead>
        <tbody>
"""

    for result in results:
        html += f"""
            <tr>
                <td><strong>{result['id']}</strong></td>
                <td>
                    <div class="intent">{result['intent']}</div>
                    <div class="style-refs">
                        <strong>실제 고객 발화 예시:</strong>
                        {result['style_refs'][0][:80]}...
                    </div>
                </td>
                <td>
                    <div class="message layer1">
                        <div class="layer-label">Layer 1 (Style Reference Injection)</div>
                        {result['layer1']}
                        <div class="meta">{len(result['layer1'])}자 | LLM 생성</div>
                    </div>

                    <div class="message layer2">
                        <div class="layer-label">Layer 2 (Utterance Transplant)</div>
                        {result['layer2']}
                        <div class="meta">{len(result['layer2'])}자 | 실제 발화 재사용</div>
                    </div>

                    <div class="message layer3">
                        <div class="layer-label">Layer 3 (Validation Loop)</div>
                        {result['layer3']}
                        <div class="meta">{len(result['layer3'])}자 | LLM 생성 + 검증</div>
                    </div>
                </td>
            </tr>
"""

    html += """
        </tbody>
    </table>

    <div style="text-align: center; color: #6c757d; margin: 40px 0;">
        <p>생성 일시: 2026-05-06 | 데이터: 차란 10,000 UserChat</p>
    </div>
</body>
</html>
"""

    output_html = Path("~/qa-agent/storage/layer_comparison.html").expanduser()
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ HTML table saved to: {output_html}")
    print(f"\n👉 브라우저에서 열어서 확인: open {output_html}")


if __name__ == "__main__":
    main()
