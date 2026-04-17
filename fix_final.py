import json
import os

# 러너가 참조할 수 있는 모든 경로의 파일을 일괄 변환합니다.
paths = [
    "/Users/eren/qa-agent/storage/runs/belier-v2/scenarios.json",
    "/Users/eren/qa-agent/projects/belier/scenarios.json",
    "/Users/eren/ax-workspace/scenarios_v2.json"
]

def fix_schema(file_path):
    if not os.path.exists(file_path): return
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "scenarios" in data: scen_list = data["scenarios"]
    elif isinstance(data, list): scen_list = data
    else: return

    new_scenarios = []
    for s in scen_list:
        # 1. 레거시가 이해하는 정확한 명칭으로 1:1 매핑
        new_s = {
            "id": s.get("id", "unknown"),
            "intent": s.get("intent", ""),
            "difficulty_tier": s.get("difficulty_tier", s.get("difficulty", "happy")),
            "persona_ref": s.get("persona_ref", s.get("customer_profile", {}l_message", s.get("conversation", [{"content":""}])[0].get("content", ""))
        }

        # 2. 평가 기준(Success Criteria) 병합 처리
        sc_raw = s.get("success_criteria", [])
        if isinstance(sc_raw, dict): sc_raw = [sc_raw]
        
        new_sc = []
        for c in sc_raw:
            nc = {"type": c.get("type", "llm_judge")}
            extra = []
            if "must_include" in c: extra.append(f"필수포함:{c['must_include']}")
            if "must_not_include" in c: extra.append(f"금지단어:{c['must_not_include']}")
            if "expected_function" in c: extra.append(f"기대함수:{c['expected_function']}(파라미터:{c.get('required_params', {})})")
            
            base_prompt = c.get("eval_prompt", c.get("description", ""))
            nc["eval_prompt"] = str(base_prompt) + (" | 검증조건: " + " ".join(extra) if extra else "")
            new_sc.append(nc)
        
        new_s["success_criteria"] = new_sc
        new_scenarios.append(new_s)

    with o.dump({"scenarios": new_scenarios}, f, ensure_ascii=False, indent=2)
    print(f"✅ {file_path} 구조 완벽 변환 완료!")

for p in paths: fix_schema(p)
