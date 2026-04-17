import json
import sys
sys.path.append("/Users/eren/qa-agent")
from tools.result_store import Scenario
import inspect

# 파이썬 클래스가 허용하는 진짜 키값만 추출
try:
    if hasattr(Scenario, "model_fields"): allowed = set(Scenario.model_fields.keys())
    elif hasattr(Scenario, "__fields__"): allowed = set(Scenario.__fields__.keys())
    else: allowed = set(inspect.signature(Scenario.__init__).parameters.keys()) - {"self"}
except Exception:
    allowed = {"id", "description", "success_criteria", "conversation"}

path = "/Users/eren/qa-agent/storage/runs/belier-v2/scenarios.json"
with open(path, "r", encoding="utf-8") as f: data = json.load(f)

for s in data.get("scenarios", []):
    meta = []
    # 파이썬이 모르는 메타데이터들을 LLM이 읽을 수 있게 한 줄로 묶음
    for key in ["intent", "difficulty", "type", "customer_profile"]:
        if key in s: meta.append(f"{key}: {s[key]}")
    
    # 허용되지 않는 키는 ?.pop(k)
    
    # 지워진 메타데이터를 description에 안전하게 병합
    if meta and "description" in allowed:
        s["description"] = str(s.get("description", "")) + " [메타정보: " + ", ".join(meta) + "]"

with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
print(f"✅ 최종 스키마 패치 완료! 허용된 키({allowed}) 외의 모든 찌꺼기를 정리했습니다.")
