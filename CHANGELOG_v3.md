# qa-agent v3 Changelog

**Date:** 2026-05-08  
**Summary:** Automated Best Practice extraction from sop-agent clustering results

## What's New

### 1. Automatic Best Practice Extraction
**Before (v2):** Manual Excel creation — DS selects BP cases, creates Excel with specific format  
**After (v3):** Automatic extraction from sop-agent clustering results

```bash
# Old way: Manual Excel
# ~/Downloads/차란 - Best Practice.xlsx (수작업)

# New way: Automatic from clustering
python3 tools/best_practice_extractor.py \
  ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  100
```

**Key Features:**
- **Proportional sampling**: Cluster size → case count
- **Quality scoring**: closed +1, CSAT +1, priority +0.5, ALF +0.5, slow -0.5
- **Balanced coverage**: All clusters represented, no manual curation needed

### 2. One-Command Pipeline
**File:** `run_bp_qa.py`

```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_$(date +%Y%m%d) \
  --target-total 100
```

Executes full pipeline:
1. Extract Best Practice (clustering-based)
2. Generate scenarios (Layer 1/2/3)
3. Execute QA tests (Playwright headless with anti-detection)
4. Save transcripts.jsonl

### 3. Updated Documentation
- **README.md**: v3 workflow, clustering-based input, new metrics
- **docs/sop-to-qa-workflow.md**: Complete 4-step guide
  - Step 1: BP extraction
  - Step 2: Scenario generation
  - Step 3: QA execution
  - Step 4: Report generation

## Workflow Comparison

### v2 Workflow
```
DS 수동 작업:
  1. UserChat 분석
  2. Best Practice Excel 작성
  3. Category/Intent 분류

qa-agent:
  4. Excel 로드
  5. 시나리오 생성
  6. QA 실행
  7. 리포트 생성
```

### v3 Workflow
```
sop-agent:
  1. UserChat clustering
  2. *_clustered.xlsx 생성

qa-agent (자동):
  3. BP 추출 (clustering 기반)
  4. 시나리오 생성
  5. QA 실행
  6. 리포트 생성
```

## Technical Details

### Best Practice Selection Algorithm

```python
# Cluster별 할당량 계산
allocation[cluster_id] = int(target_total * cluster_size / total_chats)
allocation[cluster_id] = min(allocation[cluster_id], max_per_cluster)
allocation[cluster_id] = max(allocation[cluster_id], 1)  # 최소 1개

# Quality scoring
quality_score = 0.0
  + 1.0  if state == 'closed'         # 해결됨
  + 1.0  if CSAT > 0                  # 긍정 평가
  + 0.5  if priority_tag              # 우선순위 태그
  + 0.5  if ALF triggered             # ALF 작동
  - 0.5  if time_to_answer > 1h       # 응답 지연

# Sampling
top_50_percent = sort_by(quality_score, desc).head(50%)
selected = top_50_percent.sample(allocation[cluster_id])
```

### Layer Generation

| Layer | Method | Description |
|-------|--------|-------------|
| **Layer 1** | LLM generation | Style reference from BP enhanced_text |
| **Layer 2** | Direct transplant | Extract first user message from BP |
| **Layer 3** | Layer 1 + validation | Regenerate if too short/long |

Selection strategy:
- `--layer-strategy random`: Random per case (default)
- `--layer-strategy balanced`: Equal distribution (L1, L2, L3, L1, L2, L3, ...)
- `--layer-strategy layer1/2/3`: Fixed layer for all

## Test Results

**Test run:** 벨리에v2, 5 target → 25 cases extracted (2026-05-08)

```
✅ Extracted 25 Best Practice cases

Distribution by category:
  제품_문의: 6
  노이즈: 4
  일반_문의: 2
  주문_취소_반품: 1
  교환_배송: 1
  (... 11 more categories)

Success rate: 100.0% (25/25)
Layer distribution:
  Layer 1: 13
  Layer 2: 2
  Layer 3: 10
```

## Breaking Changes

None. v2 tools (best_practice_loader.py) still work for manual Excel input.

## Migration Guide

### If you have existing manual Excel:
Keep using v2 tools:
```bash
python3 run_best_practice_test.py \
  --best-practice ~/Downloads/차란 - Best Practice.xlsx \
  --style-bank storage/charan_style_bank_100.json \
  --channel-url https://eoz6p.channel.io
```

### To use v3 with clustering:
```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  --channel-url https://eoz6p.channel.io \
  --output-dir storage/qa_run_$(date +%Y%m%d) \
  --target-total 100
```

## Next Steps

1. **Scoring agent integration**: Auto-score QA results (10-point scale)
2. **Report generation**: HTML report with BP vs ALF comparison
3. **Metrics dashboard**: Success rate, cluster coverage, intent distribution

## Files Added

- `tools/best_practice_extractor.py` — Core extraction logic
- `run_bp_qa.py` — End-to-end pipeline script
- `docs/sop-to-qa-workflow.md` — Complete workflow guide
- `CHANGELOG_v3.md` — This file

## Files Modified

- `README.md` — v3 workflow, new examples
- (v2 files unchanged — backward compatible)
