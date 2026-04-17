"""HTML presentation report generator for QA results.

Generates a customer-facing HTML presentation with:
- ChannelTalk widget UI for conversation examples
- Grid layout for multiple conversations
- Full conversation transcripts with scrollable chat bodies
- Phase-based coverage breakdown
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .result_store import Transcript, Turn, run_dir


def _pct(x: float) -> str:
    """Format as percentage."""
    return f"{x * 100:.1f}%"


def render_channeltalk_widget(
    turns: list[Turn],
    max_turns: int | None = None,
    body_bg: str = "#EDEEF2",
    label: str = "",
    note: str = "",
) -> str:
    """Render a ChannelTalk widget with full conversation.

    Args:
        turns: List of conversation turns
        max_turns: Maximum number of turns to show (None = all)
        body_bg: Background color for chat body
        label: Label above the widget
        note: Note below the widget
    """
    if max_turns:
        turns = turns[:max_turns]

    messages_html = []
    for turn in turns:
        # User message
        messages_html.append(f'''
                                <div class="ct-msg user">
                                    <div class="ct-bubble">{turn.user_message}</div>
                                </div>''')

        # ALF messages
        if turn.alf_messages:
            messages_html.append('''
                                <div class="ct-bot-name">ALF</div>''')
            for alf_msg in turn.alf_messages:
                # Replace newlines with <br> for display
                text = alf_msg.text.replace('\n', '<br>')
                messages_html.append(f'''
                                <div class="ct-msg bot">
                                    <div class="ct-avatar">A</div>
                                    <div class="ct-bubble">{text}</div>
                                </div>''')

    label_html = f'<div class="chat-label">{label}</div>' if label else ''
    note_html = f'<div class="demo-note">{note}</div>' if note else ''

    return f'''                    <div class="chat-item">
                        {label_html}
                        <div class="ct-widget">
                            <div class="ct-header">
                                <div class="ct-header-avatar">B</div>
                                <div class="ct-header-info">
                                    <div class="ct-name">벨리에 ALF</div>
                                    <div class="ct-status">응답 가능</div>
                                </div>
                            </div>
                            <div class="ct-body" style="background: {body_bg};">
{''.join(messages_html)}
                            </div>
                            <div class="ct-input">
                                <div class="ct-input-field">메시지를 입력하세요</div>
                                <div class="ct-input-send"><svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></div>
                            </div>
                        </div>
                        {note_html}
                    </div>'''


def generate_html_report(
    run_id: str,
    client_name: str,
    run_score: dict[str, Any],
    transcripts: list[Transcript],
    scenario_metadata: dict[str, dict[str, Any]],
) -> str:
    """Generate a full HTML presentation report.

    Args:
        run_id: QA run ID
        client_name: Client name for the report
        run_score: Scoring results from scoring_agent
        transcripts: List of all scenario transcripts
        scenario_metadata: Scenario metadata (intent names, weights, etc.)

    Returns:
        Complete HTML document as string
    """
    agg = run_score.get("aggregate", {})

    # Phase breakdown
    by_phase = agg.get("by_phase", {})
    p1 = by_phase.get("_phase1_summary", {})
    p2 = by_phase.get("_phase2_summary", {})

    # Convert transcripts to dict for easy lookup
    transcript_map = {t.scenario_id: t for t in transcripts}

    # Group scenarios by intent (cluster)
    scenarios_by_intent: dict[str, list[tuple[str, Transcript]]] = {}
    for scenario_id, metadata in scenario_metadata.items():
        intent = metadata.get("intent", "기타")
        if scenario_id in transcript_map:
            if intent not in scenarios_by_intent:
                scenarios_by_intent[intent] = []
            scenarios_by_intent[intent].append((scenario_id, transcript_map[scenario_id]))

    # Generate conversation examples (pick 1-2 per intent)
    conversation_widgets = []
    for intent, scenarios in scenarios_by_intent.items():
        # Take first successful scenario for this intent
        for scenario_id, transcript in scenarios[:1]:  # Limit to 1 per intent
            metadata = scenario_metadata[scenario_id]
            weight = metadata.get("weight", 0)
            label = f"✓ {intent} ({_pct(weight)})"
            note = f"✓ {len(transcript.turns)}턴 대화로 완료"

            widget = render_channeltalk_widget(
                turns=transcript.turns,
                max_turns=None,  # Show all turns
                body_bg="#EDEEF2",
                label=label,
                note=note,
            )
            conversation_widgets.append(widget)

    # Build HTML
    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{client_name} ALF 품질 검증 보고서</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
            overflow: hidden;
            background: #f8f9fa;
        }}

        .slides-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            transition: transform 0.5s ease;
        }}

        .slide {{
            min-width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 80px;
            background: white;
        }}

        .slide-content {{
            max-width: 1200px;
            width: 100%;
        }}

        h1 {{
            font-size: 3.5em;
            color: #1a1a1a;
            margin-bottom: 0.3em;
            font-weight: 700;
        }}

        h2 {{
            font-size: 2.8em;
            color: #1a1a1a;
            margin-bottom: 0.8em;
            font-weight: 600;
            border-bottom: 3px solid #007aff;
            padding-bottom: 0.3em;
        }}

        h3 {{
            font-size: 1.8em;
            color: #333;
            margin: 1.2em 0 0.6em 0;
            font-weight: 600;
        }}

        p, li {{
            font-size: 1.3em;
            line-height: 1.8;
            color: #444;
        }}

        .subtitle {{
            font-size: 1.4em;
            color: #666;
            margin-bottom: 2em;
        }}

        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            margin: 50px 0;
        }}

        .stat-box {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .stat-box.primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .stat-box.success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%);
            color: white;
        }}

        .stat-label {{
            font-size: 1.1em;
            margin-bottom: 15px;
            font-weight: 500;
            opacity: 0.9;
        }}

        .stat-value {{
            font-size: 4em;
            font-weight: 700;
            margin: 10px 0;
        }}

        .stat-desc {{
            font-size: 1em;
            opacity: 0.9;
            margin-top: 10px;
        }}

        .info-box {{
            background: #f8f9fa;
            border-left: 5px solid #007aff;
            padding: 30px;
            margin: 25px 0;
            border-radius: 8px;
        }}

        .info-box h4 {{
            font-size: 1.5em;
            color: #1a1a1a;
            margin-bottom: 0.5em;
        }}

        .success-box {{
            background: #d4edda;
            border-left: 5px solid #28a745;
            padding: 30px;
            margin: 25px 0;
            border-radius: 8px;
        }}

        .success-box h4 {{
            color: #155724;
            font-size: 1.5em;
            margin-bottom: 0.5em;
        }}

        /* ChannelTalk Chat Widget */
        .ct-widget {{
            width: 100%;
            max-width: 460px;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06);
            background: #fff;
            display: flex;
            flex-direction: column;
            margin: 25px 0;
        }}

        .ct-header {{
            background: linear-gradient(135deg, #664FFF 0%, #5A3FE8 100%);
            padding: 16px 18px;
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }}

        .ct-header-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: rgba(255,255,255,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            color: #fff;
            font-weight: 700;
            flex-shrink: 0;
        }}

        .ct-header-info {{
            color: #fff;
        }}

        .ct-header-info .ct-name {{
            font-size: 14px;
            font-weight: 700;
            line-height: 1.3;
        }}

        .ct-header-info .ct-status {{
            font-size: 11px;
            opacity: 0.75;
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .ct-header-info .ct-status::before {{
            content: '';
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #4ADE80;
        }}

        .ct-body {{
            flex: 1;
            overflow-y: auto;
            padding: 14px 14px 8px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: #EDEEF2;
            min-height: 200px;
            max-height: 280px;
        }}

        .ct-msg {{
            display: flex;
            gap: 8px;
            align-items: flex-end;
            max-width: 92%;
        }}

        .ct-msg.user {{
            align-self: flex-end;
            flex-direction: row-reverse;
        }}

        .ct-msg.bot {{
            align-self: flex-start;
        }}

        .ct-avatar {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #664FFF;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            color: #fff;
            font-weight: 700;
            flex-shrink: 0;
            margin-bottom: 2px;
        }}

        .ct-bubble {{
            padding: 10px 14px;
            border-radius: 16px;
            font-size: 13px;
            line-height: 1.6;
            max-width: 320px;
        }}

        .ct-msg.bot .ct-bubble {{
            background: #fff;
            color: #1F2937;
            border: none;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.06);
        }}

        .ct-msg.user .ct-bubble {{
            background: #664FFF;
            color: #fff;
            border-bottom-right-radius: 4px;
        }}

        .ct-bot-name {{
            font-size: 10px;
            color: #6B7280;
            font-weight: 600;
            margin-bottom: 3px;
            margin-left: 36px;
        }}

        .ct-input {{
            padding: 10px 14px;
            border-top: 1px solid rgba(0,0,0,0.06);
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
            background: #fff;
        }}

        .ct-input-field {{
            flex: 1;
            background: #F3F4F6;
            border: none;
            border-radius: 20px;
            padding: 8px 14px;
            font-size: 12px;
            color: #6B7280;
        }}

        .ct-input-send {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #664FFF;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}

        .ct-input-send svg {{
            width: 14px;
            height: 14px;
            fill: #fff;
        }}

        .chat-label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 8px;
            font-weight: 600;
        }}

        .demo-note {{
            font-size: 11px;
            color: #6B7280;
            margin-top: 10px;
            padding: 8px 12px;
            background: rgba(0,0,0,0.03);
            border-radius: 8px;
            line-height: 1.6;
        }}

        .chat-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 30px;
            margin-top: 30px;
        }}

        .chat-item {{
            display: flex;
            flex-direction: column;
        }}

        .nav-button {{
            position: fixed;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0, 122, 255, 0.9);
            color: white;
            border: none;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            font-size: 2em;
            cursor: pointer;
            z-index: 1000;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }}

        .nav-button:hover {{
            background: rgba(0, 122, 255, 1);
            transform: translateY(-50%) scale(1.1);
        }}

        .nav-button.prev {{
            left: 30px;
        }}

        .nav-button.next {{
            right: 30px;
        }}

        .slide-indicator {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 10px;
            z-index: 1000;
        }}

        .slide-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: rgba(0, 122, 255, 0.3);
            cursor: pointer;
            transition: all 0.3s;
        }}

        .slide-dot.active {{
            background: rgba(0, 122, 255, 1);
            transform: scale(1.3);
        }}
    </style>
</head>
<body>
    <div class="slides-container" id="slides">
        <!-- Slide 1: Cover -->
        <div class="slide">
            <div class="slide-content center">
                <h1>{client_name} ALF</h1>
                <h1>품질 검증 보고서</h1>
                <p class="subtitle" style="margin-top: 3em;">Run ID: {run_id}</p>
            </div>
        </div>

        <!-- Slide 2: 전체 결과 -->
        <div class="slide">
            <div class="slide-content">
                <h2>전체 검증 결과</h2>

                <div class="stat-grid">
                    <div class="stat-box success">
                        <div class="stat-label">Phase 1 관여율</div>
                        <div class="stat-value">{_pct(p1.get('coverage', 0))}</div>
                        <div class="stat-desc">지금 즉시 가능</div>
                    </div>
                    <div class="stat-box primary">
                        <div class="stat-label">Phase 2 관여율</div>
                        <div class="stat-value">{_pct(p2.get('coverage', 0))}</div>
                        <div class="stat-desc">API 연동 후</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">테스트 시나리오</div>
                        <div class="stat-value">{len(transcripts)}</div>
                        <div class="stat-desc">실제 패턴 기반</div>
                    </div>
                </div>

                <div class="info-box">
                    <h4>Phase 1 — 지금 즉시</h4>
                    <p>• 지식 문서 + 규칙만으로 {_pct(p1.get('coverage', 0))} 관여</p>
                    <p>• 추가 개발 없이 즉시 도입 가능</p>
                </div>

                <div class="info-box">
                    <h4>Phase 2 — API 연동 후</h4>
                    <p>• 주문/취소/교환 Task 포함 시 {_pct(p2.get('coverage', 0))} 관여</p>
                    <p>• API 연동 후 5영업일 내 완료</p>
                </div>
            </div>
        </div>

        <!-- Slide 3: 대화 예시 -->
        <div class="slide">
            <div class="slide-content">
                <h2>실제 테스트 대화 예시</h2>

                <div class="chat-grid">
{''.join(conversation_widgets[:4])}
                </div>
            </div>
        </div>

        <!-- Slide 4: 결론 -->
        <div class="slide">
            <div class="slide-content center">
                <h2>결론</h2>

                <p style="font-size: 1.6em; color: #666; margin-bottom: 80px;">실제 상담 기준 관여율</p>

                <div class="stat-grid">
                    <div class="stat-box success">
                        <div class="stat-label">Phase 1 (즉시)</div>
                        <div class="stat-value">{_pct(p1.get('coverage', 0))}</div>
                    </div>
                    <div class="stat-box primary">
                        <div class="stat-label">Phase 2 (5영업일)</div>
                        <div class="stat-value">{_pct(p2.get('coverage', 0))}</div>
                    </div>
                </div>

                <div class="success-box" style="margin-top: 80px;">
                    <h4>권장 진행 방식</h4>
                    <p>• <strong>Phase 1 지금 즉시 도입</strong> → 즉시 효과 확인</p>
                    <p>• <strong>Phase 2 단계적 완료</strong> → API 연동으로 최대 관여율 달성</p>
                </div>
            </div>
        </div>
    </div>

    <button class="nav-button prev" onclick="navigate(-1)">‹</button>
    <button class="nav-button next" onclick="navigate(1)">›</button>

    <div class="slide-indicator" id="indicator"></div>

    <script>
        let currentSlide = 0;
        const slides = document.querySelectorAll('.slide');
        const totalSlides = slides.length;

        // Create slide indicators
        const indicator = document.getElementById('indicator');
        for (let i = 0; i < totalSlides; i++) {{
            const dot = document.createElement('div');
            dot.className = 'slide-dot' + (i === 0 ? ' active' : '');
            dot.onclick = () => goToSlide(i);
            indicator.appendChild(dot);
        }}

        function updateSlide() {{
            document.getElementById('slides').style.transform = `translateX(-${{currentSlide * 100}}vw)`;

            // Update indicators
            document.querySelectorAll('.slide-dot').forEach((dot, i) => {{
                dot.classList.toggle('active', i === currentSlide);
            }});
        }}

        function navigate(direction) {{
            currentSlide += direction;
            if (currentSlide < 0) currentSlide = 0;
            if (currentSlide >= totalSlides) currentSlide = totalSlides - 1;
            updateSlide();
        }}

        function goToSlide(index) {{
            currentSlide = index;
            updateSlide();
        }}

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowLeft') navigate(-1);
            if (e.key === 'ArrowRight') navigate(1);
        }});
    </script>
</body>
</html>'''

    return html


def write_html_report(run_id: str, **kwargs) -> Path:
    """Write HTML report to storage/runs/<run_id>/report_client.html.

    Args:
        run_id: QA run ID
        **kwargs: Arguments to pass to generate_html_report

    Returns:
        Path to written HTML file
    """
    html = generate_html_report(run_id=run_id, **kwargs)
    output_path = run_dir(run_id) / "report_client.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path
