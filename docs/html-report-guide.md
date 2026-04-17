# HTML 보고서 생성 가이드

## 개요

qa-agent는 scoring_agent 실행 시 자동으로 고객용 HTML 프레젠테이션 보고서를 생성합니다.

**출력 경로**: `storage/runs/<run_id>/report_client.html`

## 특징

### 1. ChannelTalk 위젯 UI
- 실제 채널톡 대화창과 동일한 디자인
- 헤더, 본문, 입력창 포함
- 사용자(보라색)/봇(흰색) 말풍선 구분
- ALF 아바타 표시

### 2. 전체 대화 표시
- 1문 1답이 아닌 전체 대화 턴 표시
- 스크롤 가능한 대화창 (max-height: 280px)
- 모든 ALF 응답 메시지 포함
- 실제 테스트 transcript 그대로 반영

### 3. 그리드 레이아웃
- 2열 바둑판식 배치
- 한 화면에 여러 대화 예시 동시 표시
- 슬라이드 세로 공간 효율적 사용

### 4. 주요 지표 요약
- Phase 1/Phase 2 관여율
- Intent별 발생 비율
- 테스트 성공 여부

## 생성 방법

scoring_agent 실행 시 자동 생성:

```bash
uv run python -m tools.scoring_agent --run-id <run_id>
```

## 커스터마이징

`tools/report_html_generator.py`에서 다음 요소 수정 가능:

### 슬라이드 추가/제거

```python
def generate_html_report(...):
    html = f'''
        <!-- Slide 1: Cover -->
        <div class="slide">
            ...
        </div>
        
        <!-- 새 슬라이드 추가 -->
        <div class="slide">
            <div class="slide-content">
                <h2>새로운 섹션</h2>
                ...
            </div>
        </div>
    '''
```

### 대화 예시 선택

현재는 intent별로 첫 번째 성공 시나리오를 선택:

```python
for intent, scenarios in scenarios_by_intent.items():
    for scenario_id, transcript in scenarios[:1]:  # 첫 번째만
        ...
```

더 많은 예시를 포함하려면:

```python
for scenario_id, transcript in scenarios[:2]:  # 2개씩
```

### 색상 테마

CSS 변수로 색상 변경:

```css
.ct-header {
    background: linear-gradient(135deg, #664FFF 0%, #5A3FE8 100%);
}

.ct-msg.user .ct-bubble {
    background: #664FFF;  /* 사용자 말풍선 색 */
}
```

### 대화창 높이

```css
.ct-body {
    min-height: 200px;
    max-height: 280px;  /* 더 많은 대화를 보려면 증가 */
}
```

## 다른 고객사 적용

scoring_agent는 자동으로 다음 정보를 사용:

1. **client_name**: `config_snapshot.json`의 `extra.client_name`
2. **대화 내역**: `transcripts.jsonl`
3. **관여율 계산**: `scores.json`의 `aggregate` 데이터
4. **Intent 분류**: `scenarios.json`의 `intent` 필드

따라서 **추가 설정 없이** 모든 고객사에서 작동합니다.

## 예시

### 벨리에 ALF 보고서

```bash
# 벨리에 QA 실행
uv run python -m tools.scenario_runner \
  --run-id belier-v2-mock-20260416 \
  --channel-url https://vqnol.channel.io

# 채점 + HTML 생성
uv run python -m tools.scoring_agent \
  --run-id belier-v2-mock-20260416

# HTML 열기
open storage/runs/belier-v2-mock-20260416/report_client.html
```

### 다른 고객사 (예: 유심사)

```bash
# 유심사 QA 실행
uv run python -m tools.scenario_runner \
  --run-id yoosim-20260417 \
  --channel-url https://yoosim.channel.io

# 채점 + HTML 생성 (동일한 명령)
uv run python -m tools.scoring_agent \
  --run-id yoosim-20260417

# HTML 열기
open storage/runs/yoosim-20260417/report_client.html
```

## 트러블슈팅

### HTML 생성 실패

scoring_agent 로그에서 오류 확인:

```
[scorer] HTML report generation failed: <error message>
```

일반적 원인:
1. `transcripts.jsonl` 파일 없음
2. `scenarios.json` 파일 손상
3. Python import 오류

### 대화창이 비어있음

- `transcripts.jsonl`에 `turns`가 비어있는지 확인
- scenario_runner가 정상 실행되었는지 확인

### 스타일이 깨짐

- HTML 파일을 직접 브라우저에서 열기 (로컬 서버 불필요)
- CSS가 `<style>` 태그 안에 인라인으로 포함되어 있음

## 향후 개선 방향

1. **더 많은 슬라이드 템플릿**
   - 난이도별 성공률
   - Intent별 상세 분석
   - 타임라인 차트

2. **인터랙티브 요소**
   - 대화 예시 필터링
   - 관여율 계산 과정 시각화
   - 실시간 통계 업데이트

3. **테마 옵션**
   - 다크 모드
   - 고객사별 브랜드 컬러
   - 인쇄용 레이아웃
