#!/usr/bin/env python3
"""
Phase 1: Normalize sop-agent v2 output to canonical YAML

Uses normalize_sop.md prompt with Sonnet 4.6 via Prism gateway.
"""

import os
import json
import anthropic
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

# Prism Gateway config
PRISM_BASE_URL = "https://prism.ch.dev"
PRISM_MODEL = "anthropic/claude-sonnet-4-6"  # Sonnet 4.6 via Prism (provider prefix required)

# Paths
SOP_RESULTS_DIR = Path("/Users/eren/sop-agent/results/벨리에v2")
RUN_DIR = Path("/Users/eren/qa-agent/storage/runs/r-20260416-152509")
PROMPTS_DIR = Path("/Users/eren/qa-agent/prompts")

def load_prompt() -> str:
    """Load normalize_sop.md prompt"""
    prompt_path = PROMPTS_DIR / "normalize_sop.md"
    return prompt_path.read_text(encoding="utf-8")

def load_source_files() -> dict:
    """Load all required source files from sop-agent v2 output"""
    files = {}

    # Required files
    files["metadata"] = json.loads((SOP_RESULTS_DIR / "03_sop" / "metadata.json").read_text(encoding="utf-8"))
    files["faq"] = json.loads((SOP_RESULTS_DIR / "02_extraction" / "faq.json").read_text(encoding="utf-8"))

    # patterns.json - read first 1000 lines to avoid token limit
    patterns_path = SOP_RESULTS_DIR / "02_extraction" / "patterns.json"
    with open(patterns_path, encoding="utf-8") as f:
        patterns_text = "".join(f.readlines()[:1000])  # First 1000 lines should cover metadata + clusters
    files["patterns_partial"] = patterns_text

    files["pipeline_summary"] = (SOP_RESULTS_DIR / "pipeline_summary.md").read_text(encoding="utf-8")
    files["automation_analysis"] = (SOP_RESULTS_DIR / "05_sales_report" / "analysis" / "automation_analysis.md").read_text(encoding="utf-8")

    # Task JSON files - extract only essential metadata to reduce token count
    task_json_dir = SOP_RESULTS_DIR / "04_tasks_json"
    files["tasks"] = []
    for task_file in sorted(task_json_dir.glob("TASK*.json")):
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
        # Extract only essential fields to reduce token count
        task_meta = {
            "filename": task_file.name,
            "name": task_data["task"]["name"],
            "trigger": task_data["task"]["trigger"][:500] + "..." if len(task_data["task"]["trigger"]) > 500 else task_data["task"]["trigger"],  # Truncate long trigger
            "node_count": len(task_data["task"]["nodes"]),
            "has_app_functions": any(n.get("functionType") == "app" for n in task_data["task"]["nodes"]),
            "function_keys": list(set(n.get("functionKey", "") for n in task_data["task"]["nodes"] if n.get("functionType") == "app"))
        }
        files["tasks"].append(task_meta)

    return files

def build_user_message(prompt: str, files: dict) -> str:
    """Build user message with prompt + source files"""

    msg = f"""{prompt}

---

## Input Files

### metadata.json
```json
{json.dumps(files["metadata"], ensure_ascii=False, indent=2)}
```

### faq.json
```json
{json.dumps(files["faq"], ensure_ascii=False, indent=2)}
```

### patterns.json (partial - metadata + first clusters)
```json
{files["patterns_partial"]}
```

### pipeline_summary.md
```markdown
{files["pipeline_summary"]}
```

### automation_analysis.md
```markdown
{files["automation_analysis"]}
```

### Task JSON Files
"""

    for task in files["tasks"]:
        msg += f"""
#### {task["filename"]}
- Name: {task["name"]}
- Trigger (excerpt): {task["trigger"]}
- Node count: {task["node_count"]}
- Has external API calls: {task["has_app_functions"]}
- Function keys: {", ".join(task["function_keys"]) if task["function_keys"] else "None"}
"""

    msg += """

---

Generate the canonical_input.yaml following the schema and normalization rules above.
Output YAML only, no surrounding prose or code fence.
"""

    return msg

def main():
    print("Phase 1: Normalizing sop-agent v2 output to canonical YAML")
    print(f"Run ID: r-20260416-152509")
    print(f"Client: 벨리에 (BELIER)")
    print(f"Coverage mode: rag_only")
    print()

    # Load files
    print("Loading source files...")
    prompt = load_prompt()
    files = load_source_files()
    print(f"  ✓ Loaded metadata.json ({files['metadata']['total_sops']} SOPs)")
    print(f"  ✓ Loaded faq.json ({files['faq']['metadata']['total_faq_pairs']} FAQ pairs)")
    print(f"  ✓ Loaded patterns.json (partial)")
    print(f"  ✓ Loaded pipeline_summary.md")
    print(f"  ✓ Loaded automation_analysis.md")
    print(f"  ✓ Loaded {len(files['tasks'])} task JSON files")
    print()

    # Build message
    print("Building user message...")
    user_message = build_user_message(prompt, files)
    print(f"  ✓ Message length: {len(user_message):,} chars")
    print()

    # Call API via Prism
    print(f"Calling Anthropic API via Prism ({PRISM_MODEL})...")
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        base_url=PRISM_BASE_URL
    )

    response = client.messages.create(
        model=PRISM_MODEL,
        max_tokens=16000,
        temperature=0.0,
        timeout=120.0,  # 2 minute timeout
        messages=[{
            "role": "user",
            "content": user_message
        }]
    )

    # Extract YAML
    yaml_output = response.content[0].text
    print(f"  ✓ Received response ({len(yaml_output):,} chars)")
    print()

    # Save to file
    output_path = RUN_DIR / "canonical_input.yaml"
    output_path.write_text(yaml_output, encoding="utf-8")
    print(f"✓ Saved canonical_input.yaml to:")
    print(f"  {output_path}")
    print()

    # Show preview
    print("Preview (first 50 lines):")
    print("─" * 80)
    lines = yaml_output.split("\n")
    for line in lines[:50]:
        print(line)
    if len(lines) > 50:
        print(f"... ({len(lines) - 50} more lines)")
    print("─" * 80)
    print()
    print("Phase 1 complete.")

if __name__ == "__main__":
    main()
