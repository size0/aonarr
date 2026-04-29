import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_tmp_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp_data.name

from app.services.llm_client import LLMClientError, completion_url, estimate_cost, parse_json_object
from app.services.prompt_templates import render_prompt_template
from app.services.serial_engine import bool_value, number_value


assert completion_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
assert (
    completion_url("http://localhost:11434/v1/chat/completions")
    == "http://localhost:11434/v1/chat/completions"
)
assert parse_json_object('```json\n{"title_hint":"A","cast_ids":[]}\n```')["title_hint"] == "A"

try:
    parse_json_object("not json")
except LLMClientError as exc:
    assert exc.code == "llm_invalid_plan_json"
else:
    raise AssertionError("parse_json_object should reject invalid JSON")

profile = {"cost_per_1k_input_tokens": 0.01, "cost_per_1k_output_tokens": 0.03}
assert estimate_cost(profile, 1000, 2000) == 0.07
assert number_value("8.6", 0) == 8.6
assert number_value("99", 0) == 10
assert bool_value("accepted", False) is True
assert bool_value("rejected", True) is False
outline_prompt = render_prompt_template(
    "serial_outline",
    {
        "project_title": "A",
        "genre": "Fantasy",
        "style_goal": "Fast",
        "target_chapter_count": 300,
        "target_words_per_chapter": 2000,
        "outline_range": "Full book",
        "bible_context": "Premise: test",
        "existing_outline_context": "None",
    },
)
assert "senior web-novel architect" in outline_prompt["messages"][0]["content"]
assert "Workflow stage: SERIAL_OUTLINE" in outline_prompt["messages"][1]["content"]
assert "第X卷：卷名" in outline_prompt["messages"][1]["content"]
prompt = render_prompt_template(
    "serial_plan",
    {
        "project_title": "A",
        "genre": "Fantasy",
        "style_goal": "Fast",
        "target_words_per_chapter": 1000,
        "chapter_number": 1,
        "bible_context": "Premise: test",
    },
)
assert prompt["messages"][0]["role"] == "system"
assert "senior web-novel story editor" in prompt["messages"][0]["content"]
assert "Project title: A" in prompt["messages"][1]["content"]
assert "Workflow stage: CHAPTER_PLAN" in prompt["messages"][1]["content"]
assert "context_dependencies" in prompt["messages"][1]["content"]
revision_prompt = render_prompt_template(
    "serial_revision",
    {
        "project_title": "A",
        "genre": "Fantasy",
        "style_goal": "Fast",
        "target_words_per_chapter": 1000,
        "bible_context": "Premise: test",
        "chapter_title_hint": "T",
        "chapter_goal": "G",
        "chapter_conflict": "C",
        "chapter_hook": "H",
        "review_summary": "Needs stronger hook.",
        "previous_draft_body": "Old draft",
    },
)
assert "Review feedback: Needs stronger hook." in revision_prompt["messages"][1]["content"]
assert "Revision rules:" in revision_prompt["messages"][1]["content"]

print("unit_check_ok")
