"""一次性脚本：创建多个 LLM Profile 并按阶段绑定"""
import urllib.request
import json

BASE = "http://127.0.0.1:8101/api/v1/settings/llm"


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read()) if r.status != 204 else {}
    except Exception as e:
        print(f"  WARN: {method} {path} -> {e}")
        return None


def main():
    # 1. Delete old profiles
    config = api("GET", "/config")
    for p in config.get("profiles", []):
        print(f"Deleting old profile: {p['name']}")
        api("DELETE", f"/profiles/{p['id']}")

    # 2. Create new profiles
    profiles_def = [
        ("Claude Opus 4.6 Thinking", "claude-opus-4.6-thinking", 0.78, 8192, 600,
         "正文写作主力，质量第一"),
        ("Gemini 3.1 Pro High", "gemini-3.1-pro-high", 0.7, 8192, 300,
         "规划/分析/审核/预测，结构化推理强"),
        ("Gemini 2.5 Flash", "gemini-2.5-flash", 0.3, 4096, 120,
         "高频提取任务，快速准确"),
        ("Claude Opus 4.7 Medium", "claude-opus-4-7-medium", 0.6, 4096, 300,
         "文风/语感/优化，Claude语感最强"),
    ]

    pid_map = {}
    for name, model, temp, max_t, timeout, notes in profiles_def:
        result = api("POST", "/profiles", {
            "name": name, "protocol": "openai",
            "base_url": "http://120.48.178.14:3003/v1",
            "api_key": "windsurf", "model": model,
            "temperature": temp, "max_tokens": max_t,
            "timeout_seconds": timeout, "notes": notes,
        })
        if result:
            pid = result["id"]
            pid_map[model] = pid
            print(f"  Created: {name} ({model}) -> {pid[:8]}...")

    # 3. Bind stages
    bindings = {
        "chapter_writing": "claude-opus-4.6-thinking",
        "outline_planning": "gemini-3.1-pro-high",
        "post_chapter_pipeline": "gemini-2.5-flash",
        "book_analysis_extract": "gemini-2.5-flash",
        "book_analysis_deep": "gemini-3.1-pro-high",
        "style_detection": "claude-opus-4-7-medium",
        "audit_review": "gemini-3.1-pro-high",
        "learning_agent": "gemini-2.5-flash",
        "prompt_optimization": "claude-opus-4-7-medium",
        "prediction": "gemini-3.1-pro-high",
    }

    for stage, model in bindings.items():
        if model in pid_map:
            api("POST", "/bind-stage", {"stage": stage, "profile_id": pid_map[model]})
            print(f"  Bound: {stage} -> {model}")
        else:
            print(f"  SKIP: {stage} (no profile for {model})")

    print("\nDone! All profiles and bindings configured.")


if __name__ == "__main__":
    main()
