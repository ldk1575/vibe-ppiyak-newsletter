"""
tools/robustness_checks.py - PRD '통과 기준' 중 일부러 망가뜨려 봐야 확인되는 것들을 한 번에 돌린다.

  C1 금지 소스를 채택 목록에 넣으면 수집 단계에서 실행이 거부된다        (LLM 없음)
  C2 존재하지 않는 소스 URL 이 섞여도 나머지 소스로 수집이 계속된다        (네트워크)
  C3 숫자 대조 규칙: 원문 숫자를 바꾼 요약은 걸리고, 정확한 요약은 안 걸린다 (LLM 없음)
  C4 LLM 검수: 원문에 없는 기능을 지어낸 요약을 불통과시킨다              (LLM 1회)
  C5 키워드 단어 경계: crypto 가 cryptography 에 걸리지 않는다             (LLM 없음)

실행: python tools/robustness_checks.py  → store/robustness_checks.json, 하나라도 실패하면 종료 코드 1
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import graph  # noqa: E402

SOURCE = (
    "Toolbox MCP is an open-source MCP server written in Python. It lets Claude Code and Cursor call 12 local tools "
    "such as file search and shell commands. Install with `pip install toolbox-mcp` and run `toolbox-mcp serve`. "
    "The project reached 3,400 stars in its first week. It supports macOS and Linux; Windows support is planned."
)
GOOD = (
    "- Toolbox MCP는 Python으로 만든 오픈소스 MCP 서버예요.\n"
    "- Claude Code와 Cursor가 파일 검색·셸 명령 같은 로컬 도구 12개를 부를 수 있게 해 줘요.\n"
    "- 첫 주에 스타 3,400개를 받았고 macOS·Linux를 지원해요."
)
WRONG_NUMBER = GOOD.replace("3,400", "34,000").replace("12개", "120개")
FAKE_FEATURE = (
    "- Toolbox MCP는 Python으로 만든 오픈소스 MCP 서버예요.\n"
    "- Windows 전용 GUI 설치 프로그램과 클라우드 동기화 기능을 기본으로 제공해요.\n"
    "- 브라우저 자동화와 이미지 생성 도구도 내장되어 있어요."
)
INSIGHT = "Claude Code 실습에서 `pip install toolbox-mcp` 후 `toolbox-mcp serve`로 띄우면 내 컴퓨터 파일을 찾는 에이전트를 바로 만들어 볼 수 있어요."


def c1_forbidden_source(base: dict) -> dict:
    cfg = copy.deepcopy(base)
    cfg["sources"]["adopted"][0]["url"] = "https://techcrunch.com/category/artificial-intelligence/feed/"
    state = graph.load_config_node({})
    state["audience_config"] = cfg
    try:
        graph.collect_rss_node(state)
        return {"passed": False, "detail": "금지 소스인데 수집이 진행됨"}
    except ValueError as e:
        return {"passed": True, "detail": str(e)}


def c2_broken_source(base: dict) -> dict:
    cfg = copy.deepcopy(base)
    cfg["sources"]["adopted"][1] = {**cfg["sources"]["adopted"][1], "url": "https://news.hada.io/rss/does-not-exist", "backup_url": None}
    state = graph.load_config_node({})
    state["audience_config"] = cfg
    out = graph.collect_rss_node(state)
    counts, errors = out["metrics"]["source_counts"], out["metrics"]["source_errors"]
    others = [v for k, v in counts.items() if k != cfg["sources"]["adopted"][1]["id"] and not k.endswith("_dropped")]
    ok = cfg["sources"]["adopted"][1]["id"] in errors and sum(others) > 0
    return {"passed": ok, "detail": {"source_counts": counts, "source_errors": errors}}


def c3_number_rule() -> dict:
    caught = graph.numbers_not_in_source(WRONG_NUMBER, SOURCE)
    clean = graph.numbers_not_in_source(GOOD + " " + INSIGHT, SOURCE)
    return {"passed": bool(caught) and not clean, "detail": {"wrong_summary_flags": caught, "good_summary_flags": clean}}


def c4_llm_fake_feature(base: dict) -> dict:
    from graph import EVAL_PROMPT, EvaluationOutput, call_llm, get_llm

    checks = "\n".join(f"{i}. {c}" for i, c in enumerate(base["evaluation_and_retry"]["checks"], 1))
    chain = EVAL_PROMPT | get_llm(0.0, os.getenv("EVAL_THINKING_LEVEL", "medium")).with_structured_output(EvaluationOutput)
    res = call_llm("check", chain, {"checks": checks, "title": "Toolbox MCP", "url": "https://github.com/example/toolbox-mcp",
                                    "full_text": SOURCE, "summary": FAKE_FEATURE, "beginner_insight": INSIGHT,
                                    "difficulty_stars": "🐣 쉬움 ★☆☆", "body_source": "readme", "body_chars": len(SOURCE)})
    return {"passed": res.passed is False, "detail": {"llm_passed": res.passed, "feedback": res.feedback}}


def c5_keyword_boundary() -> dict:
    a = graph.keyword_hit("A tiny cryptography library for Rust", ["crypto"])
    b = graph.keyword_hit("Crypto exchange hiring now", ["crypto"])
    c = graph.keyword_hit("클로드 코드 에이전트 실습", ["에이전트"])
    return {"passed": a is None and b == "crypto" and c == "에이전트", "detail": {"cryptography": a, "crypto": b, "korean": c}}


def main() -> int:
    load_dotenv(ROOT / ".env")
    sys.stdout.reconfigure(encoding="utf-8")
    import yaml

    base = yaml.safe_load((ROOT / "audience.yaml").read_text(encoding="utf-8"))
    results = {
        "C1_forbidden_source_rejected": c1_forbidden_source(base),
        "C2_broken_source_isolated": c2_broken_source(base),
        "C3_number_rule": c3_number_rule(),
        "C4_llm_catches_fake_feature": c4_llm_fake_feature(base),
        "C5_keyword_word_boundary": c5_keyword_boundary(),
    }
    for name, r in results.items():
        print(f"{'✅' if r['passed'] else '❌'} {name}: {json.dumps(r['detail'], ensure_ascii=False)[:300]}")
    out = {"checked_at": datetime.now(timezone.utc).isoformat(), "results": results}
    (ROOT / "store").mkdir(exist_ok=True)
    (ROOT / "store" / "robustness_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
