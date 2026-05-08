# Manual Best Practice Selection Guide

qa-agent v3는 두 가지 BP 선정 방식을 지원합니다:

1. **자동 추출** (기본): sop-agent clustering 결과에서 자동으로 선정
2. **수동 지정**: 사용자가 원하는 UserChat을 직접 지정

## 수동 지정 방법

### 1. 수동 BP 파일 생성

UserChat ID 또는 URL을 포함한 파일을 작성합니다.

**지원 형식:**
- `.tsv` (Tab-separated values)
- `.csv` (Comma-separated values)  
- `.xlsx` / `.xls` (Excel)

**필수 컬럼:**
- `user_chat_id` 또는 `url` (둘 중 하나 이상)

**선택 컬럼:**
- `intent`, `category` (자동으로 clustering Excel에서 매칭)

### 2. 파일 예시

**TSV 형식 (`manual_bp.tsv`):**
```tsv
user_chat_id	intent	category
6997a6f8bc02a881342e	데님 팬츠 재입고 문의	제품_문의
6981fe3c37a26d3d48a5	반품 수거 지연	주문_취소_반품
6988780ceba5a39d52bd	교환 신청	교환_배송
```

**CSV 형식 (`manual_bp.csv`):**
```csv
user_chat_id,intent,category
6997a6f8bc02a881342e,데님 팬츠 재입고 문의,제품_문의
6981fe3c37a26d3d48a5,반품 수거 지연,주문_취소_반품
6988780ceba5a39d52bd,교환 신청,교환_배송
```

**URL 방식 (`manual_bp_urls.tsv`):**
```tsv
url
https://desk.channel.io/ovxd4/user-chats/6997a6f8bc02a881342e
https://desk.channel.io/ovxd4/user-chats/6981fe3c37a26d3d48a5
https://desk.channel.io/ovxd4/user-chats/6988780ceba5a39d52bd
```

### 3. QA 실행

```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_manual \
  --manual-bp manual_bp.tsv \
  --timeout 120.0
```

**주요 옵션:**
- `--manual-bp`: 수동 BP 파일 경로 (TSV/CSV/Excel)
- `--clustered-excel`: clustering 결과 (BP 상세 정보 조회용)
- `--target-total`, `--min-cluster-size`: **무시됨** (수동 지정 시)

### 4. 출력 확인

```bash
# 실행 로그
cat storage/qa_manual.log

# 결과
ls storage/qa_manual/transcripts.jsonl
```

실행 시 다음과 같이 표시됩니다:

```
======================================================================
Step 1: Extract Best Practice
======================================================================
Mode: Manual selection
Manual BP file: manual_bp.tsv
Clustered Excel: .../벨리에_clustered.xlsx

📋 Manual BP: 3 user chat IDs specified
✓ Matched 3/3 cases in clustering data
✅ Extracted 3 Best Practice cases

Distribution by category:
  제품_문의: 1
  교환_배송: 1
  주문_취소_반품: 1
```

## 언제 수동 지정을 사용하나?

### 자동 추출 (추천)
- **일반적인 QA**: 전체 의도 커버리지 확인
- **볼륨 기반 분석**: 실제 고객 분포 반영
- **빠른 테스트**: 설정만으로 즉시 실행

### 수동 지정
- **특정 케이스 검증**: 문제가 발생한 특정 UserChat 재현
- **엣지 케이스 테스트**: 자동 추출에서 누락된 희귀 케이스
- **커스텀 시나리오**: DS가 직접 큐레이션한 케이스
- **회귀 테스트**: 이전에 실패했던 케이스 재검증

## UserChat ID 찾는 방법

### 1. 채널톡 Desk URL에서
```
https://desk.channel.io/ovxd4/user-chats/6997a6f8bc02a881342e
                                          ^^^^^^^^^^^^^^^^^^^^
                                          이 부분이 user_chat_id
```

### 2. Clustering Excel에서
```bash
# Excel에서 검색하여 id 컬럼 복사
open ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx
```

### 3. Langfuse MCP로 검색
```python
# Claude에서 직접 검색 가능
"벨리에 '반품' 관련 UserChat 찾아줘"
```

## 조합 사용

수동 지정과 자동 추출을 여러 번 실행하여 조합할 수 있습니다:

```bash
# 1. 자동 추출로 전체 커버리지 확인
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_auto \
  --target-total 100

# 2. 수동 지정으로 특정 케이스 추가 검증
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_manual \
  --manual-bp critical_cases.tsv
```

## 에러 처리

### "No matching user chats found"
→ user_chat_id가 clustering Excel에 없음
- clustering Excel의 `id` 컬럼에서 정확한 ID 확인
- 다른 고객사 데이터를 참조하고 있는지 확인

### "Manual BP file must contain 'user_chat_id' or 'url' column"
→ 컬럼명 오타 또는 누락
- 정확한 컬럼명 사용: `user_chat_id` (언더스코어 2개)
- 또는 `url` 사용

### "Unsupported manual BP file format"
→ 지원하지 않는 파일 형식
- `.tsv`, `.csv`, `.xlsx`, `.xls`만 지원
- 파일 확장자 확인

## 예제 파일

qa-agent repo에 예제 파일이 포함되어 있습니다:

```bash
# 복사하여 수정
cp manual_bp_example.tsv my_bp.tsv
vi my_bp.tsv  # UserChat ID 수정

# 실행
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_my_bp \
  --manual-bp my_bp.tsv
```
