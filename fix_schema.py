import json
import sys
sys.path.append("/Users/eren/qa-agent")
from tools.result_store import SuccessCriterion

# 허용 키 추출
if hasattr(SuccessCriterion, "model_fields"): allowed_keys = set(SuccessCriterion.model_fields.keys())
elif hasattr(SuccessCriterion, "__fields__"): allowed_keys = set(SuccessCriterion.__fields__.keys())
else: 
    import inspect
    allowed_keys = set(inspect.signature(SuccessCriterion).parameters.keys())

path = "/Users/eren/qa-agent/storage/runs/belier-v2/scenarios.json"
with open(path, "r", encoding="utf-8") as f: data = json.load(f)

for s in data.get("scenarios", []):
    for c in s.get("success_criteria", []):
        extra_info = []
        if "must_include" in c: extra_info.append(f"필수포함:{c['must_include']}")
        if "must_not_include" in c: extra_info.append(f"금지단어:{c['must_not_include']}")
        if "expected_function" in c:
            params = c.get("required_params", {})
            extra_info.append(f"기대???:{params})")
        
        keys_to_remove = [k for k in list(c.keys()) if k not in allowed_keys]
        for k in keys_to_remove: c.pop(k)
        
        if extra_info:
            target_key = "eval_prompt" if "eval_prompt" in allowed_keys else ("description" if "description" in allowed_keys else None)
            if target_key:
                c[target_key] = str(c.get(target_key, "")) + " | 검증조건: " + " ".join(extra_info)

with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
print(f"✅ JSON 스키마 호환성 패치 완료! 기존 파이썬 클래스 허용 키: {allowed_keys}")
