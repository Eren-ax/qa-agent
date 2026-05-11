#!/usr/bin/env python3
"""
차란 Best Practice QA 리포트의 메트릭을 수정하는 스크립트

문제:
- 모든 케이스의 메트릭이 0으로 표시됨 (턴수 0턴, 응대시간 0초, 토큰 0)

수정 사항:
1. 턴 수 계산: len(transcript['turns'])
2. 응대 시간 계산: (ended_at - started_at).total_seconds()
3. 토큰 사용량: transcript에 없으므로 메트릭에서 제거
4. 전체 요약 통계 업데이트
5. 결과 상태(terminated_reason) 올바르게 매핑
"""

import json
import os
from datetime import datetime
from pathlib import Path


def calculate_metrics(transcript):
    """transcript 데이터에서 메트릭 계산"""
    metrics = {}

    # 1. 턴 수 계산
    metrics['turns'] = len(transcript.get('turns', []))

    # 2. 응대 시간 계산
    try:
        started_at = transcript.get('started_at', '')
        ended_at = transcript.get('ended_at', '')

        if started_at and ended_at:
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
            metrics['duration_seconds'] = (end_time - start_time).total_seconds()
        else:
            metrics['duration_seconds'] = 0.0
    except Exception as e:
        print(f"Warning: 응대 시간 계산 실패 - {e}")
        metrics['duration_seconds'] = 0.0

    # 3. 평균 응답 시간 계산 (턴당)
    if metrics['turns'] > 0:
        metrics['avg_response_time'] = metrics['duration_seconds'] / metrics['turns']
    else:
        metrics['avg_response_time'] = 0.0

    return metrics


def map_terminated_reason(reason):
    """terminated_reason을 한국어 상태로 매핑"""
    mapping = {
        'completed': '✅ 성공',
        'escalated': '⚠️ 부분 성공',
        'timeout': '⏱️ 타임아웃',
        'error': '❌ 오류',
        'max_turns': '⚠️ 최대 턴 도달'
    }
    return mapping.get(reason, f'⭐ {reason.upper()}')


def format_metrics_section(metrics):
    """메트릭 섹션 마크다운 생성 (토큰 사용량 제거)"""
    return f"""### 📈 메트릭
- **턴 수:** {metrics['turns']}턴
- **응대 시간:** {metrics['duration_seconds']:.1f}초
- **평균 응답 시간:** {metrics['avg_response_time']:.1f}초 (턴당)"""


def process_report():
    """리포트 파일을 읽어 메트릭 수정"""

    # 경로 설정
    storage_dir = Path('/Users/eren/qa-agent/storage/bp_test')
    data_file = storage_dir / 'merged_analysis.json'
    input_report = storage_dir / 'QA_REPORT_차란_Best_Practice_v3.md'
    output_report_md = storage_dir / 'QA_REPORT_차란_Best_Practice_v4.md'
    output_report_html = storage_dir / 'QA_REPORT_차란_Best_Practice_v4.html'

    # 데이터 파일 확인
    if not data_file.exists():
        print(f"❌ 데이터 파일을 찾을 수 없습니다: {data_file}")
        return False

    if not input_report.exists():
        print(f"❌ 입력 리포트를 찾을 수 없습니다: {input_report}")
        return False

    # JSON 데이터 로드
    print(f"📂 데이터 로드 중: {data_file}")
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"📊 총 {len(data)} 개 케이스 발견")

    # 전체 통계 계산
    total_turns = 0
    total_duration = 0.0
    result_counts = {}

    case_metrics = {}

    for idx, case in enumerate(data, 1):
        case_id = f'case_{idx}'
        # transcript 키가 중첩되어 있음: case['transcript']['transcript']
        outer_transcript = case.get('transcript', {})
        transcript = outer_transcript.get('transcript', {})

        # 메트릭 계산
        metrics = calculate_metrics(transcript)
        case_metrics[case_id] = metrics

        total_turns += metrics['turns']
        total_duration += metrics['duration_seconds']

        # 결과 상태 집계
        terminated_reason = transcript.get('terminated_reason', 'UNKNOWN')
        result_status = map_terminated_reason(terminated_reason)
        result_counts[result_status] = result_counts.get(result_status, 0) + 1

    # 평균 계산
    num_cases = len(data)
    avg_turns = total_turns / num_cases if num_cases > 0 else 0.0
    avg_duration = total_duration / num_cases if num_cases > 0 else 0.0

    print(f"\n📊 전체 통계:")
    print(f"  - 평균 턴 수: {avg_turns:.1f}턴")
    print(f"  - 평균 응대 시간: {avg_duration:.1f}초")
    print(f"  - 결과 상태 분포:")
    for status, count in sorted(result_counts.items()):
        print(f"    {status}: {count}개")

    # 기존 리포트 읽기
    print(f"\n📝 기존 리포트 읽기: {input_report}")
    with open(input_report, 'r', encoding='utf-8') as f:
        report_lines = f.readlines()

    # 리포트 수정
    print("✏️  메트릭 수정 중...")
    new_lines = []
    current_case = None
    current_case_index = 0
    in_metrics_section = False
    skip_until_separator = False

    for i, line in enumerate(report_lines):
        # 케이스 시작 감지
        if line.startswith('## ') and not line.startswith('## 📊'):
            # 케이스 번호 추출
            parts = line.split('.')
            if len(parts) >= 2:
                try:
                    case_num = int(parts[0].replace('##', '').strip())
                    current_case = f"case_{case_num}"
                    current_case_index = case_num - 1
                except ValueError:
                    pass
            in_metrics_section = False
            skip_until_separator = False

        # 결과 상태 수정
        if line.startswith('**결과:**'):
            if current_case_index < len(data):
                outer_transcript = data[current_case_index].get('transcript', {})
                transcript = outer_transcript.get('transcript', {})
                terminated_reason = transcript.get('terminated_reason', 'UNKNOWN')
                result_status = map_terminated_reason(terminated_reason)
                new_lines.append(f"**결과:** {result_status}\n")
                continue

        # 전체 요약 섹션 감지 및 수정
        if line.startswith('## 📊 전체 요약'):
            new_lines.append(line)
            # 다음 11줄(전체 요약 내용)을 새로운 통계로 교체
            for _ in range(11):
                if i + 1 < len(report_lines):
                    next(iter(report_lines[i+1:]))  # 다음 줄 건너뛰기

            # 새로운 전체 요약 작성
            new_lines.append(f"- **전체 케이스:** {num_cases}개\n")

            # 결과 상태별 집계 (이모지 포함)
            for status, count in sorted(result_counts.items()):
                new_lines.append(f"- **{status}:** {count}개\n")

            new_lines.append(f"- **평균 응대 시간:** {avg_duration:.1f}초\n")
            new_lines.append(f"- **평균 턴 수:** {avg_turns:.1f}턴\n")
            new_lines.append('\n')
            skip_until_separator = True
            continue

        # 구분선(---)까지 건너뛰기
        if skip_until_separator:
            if line.strip().startswith('---'):
                skip_until_separator = False
                new_lines.append(line)
            continue

        # 메트릭 섹션 시작 감지
        if line.startswith('### 📈 메트릭'):
            in_metrics_section = True
            # 현재 케이스의 메트릭으로 교체
            if current_case and current_case in case_metrics:
                metrics = case_metrics[current_case]
                new_lines.append(format_metrics_section(metrics) + '\n')
                # 다음 4줄(기존 메트릭)을 건너뛰기
                continue
            else:
                new_lines.append(line)
                continue

        # 메트릭 섹션 내부 라인은 건너뛰기
        if in_metrics_section:
            if line.startswith('- **') or line.strip() == '':
                continue
            else:
                in_metrics_section = False

        new_lines.append(line)

    # 수정된 리포트 저장 (Markdown)
    print(f"\n💾 수정된 리포트 저장 중: {output_report_md}")
    with open(output_report_md, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    # HTML 버전 생성
    print(f"🌐 HTML 버전 생성 중: {output_report_html}")
    try:
        import markdown

        # Markdown to HTML 변환
        md_content = ''.join(new_lines)
        html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])

        # HTML 템플릿
        html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>차란 Best Practice QA 리포트 v4</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1, h2, h3 {{
            color: #333;
        }}
        h1 {{
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            border-bottom: 2px solid #2196F3;
            padding-bottom: 8px;
            margin-top: 40px;
        }}
        h3 {{
            color: #555;
            margin-top: 30px;
        }}
        ul {{
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        blockquote {{
            background-color: #f9f9f9;
            border-left: 4px solid #4CAF50;
            padding: 10px 20px;
            margin: 10px 0;
        }}
        hr {{
            border: none;
            border-top: 2px solid #ddd;
            margin: 40px 0;
        }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""

        with open(output_report_html, 'w', encoding='utf-8') as f:
            f.write(html_template)

        print("✅ HTML 버전 생성 완료")
    except ImportError:
        print("⚠️  markdown 패키지가 설치되어 있지 않아 HTML 생성을 건너뜁니다.")
        print("   pip install markdown 으로 설치 후 다시 실행하세요.")

    print(f"\n✅ 리포트 메트릭 수정 완료!")
    print(f"   - Markdown: {output_report_md}")
    print(f"   - HTML: {output_report_html}")

    return True


if __name__ == '__main__':
    success = process_report()
    exit(0 if success else 1)
