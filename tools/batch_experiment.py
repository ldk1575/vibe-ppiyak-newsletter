"""
tools/batch_experiment.py - 예선 batch_size 를 실측으로 정한다.

같은 후보(오늘 수집 → 규칙 필터 통과분)를 batch 5 / 10 / 30 으로 예선 판정하고 비교한다.
  - calls        : LLM 호출 수 (무료 한도·비용과 직결)
  - seconds      : 예선 전체 소요 시간 (레이트 리미터 대기 포함)
  - missing_rate : 묶음 안에서 판정이 빠진 기사 비율 (Lost-in-the-Middle·JSON 누락의 대리 지표)
  - pass_rate    : 통과 비율
  - agreement    : 세 크기의 다수결 판정과 일치한 비율 (판정 일관성)

실행: python tools/batch_experiment.py  → store/batch_experiment.json
주의: LLM 을 호출한다 (후보 60건 기준 약 12+6+2 = 20회).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import graph  # noqa: E402

SIZES = [5, 10, 30]


def main() -> None:
    load_dotenv(ROOT / ".env")
    sys.stdout.reconfigure(encoding="utf-8")
    state = graph.load_config_node({})
    state.update(graph.collect_rss_node(state))
    config = state["audience_config"]
    pre = config["selection_criteria"]["preliminary"]
    candidates = [
        a for a in state["raw_articles"]
        if not graph.keyword_hit(f"{a['title']} {a['raw_summary']} {a['url']}", pre["exclude_keywords"])
    ]
    print(f"후보 {len(candidates)}건 (수집 {len(state['raw_articles'])}건, 소스별 {state['metrics']['source_counts']})")

    results = {}
    for size in SIZES:
        r = graph.run_prelim_batches(candidates, size, config)
        verdicts = {i: d.passed for i, d in r["decisions"].items()}
        results[size] = {"stats": r["stats"], "verdicts": verdicts}
        passed = sum(verdicts.values())
        print(f"batch={size:>2}: 호출 {r['stats']['calls']}회 · {r['stats']['seconds']}초 · "
              f"누락 {r['stats']['missing']}건({r['stats']['missing_rate_pct']}%) · 통과 {passed}건")

    rows = []
    for size in SIZES:
        agree = total = 0
        for a in candidates:
            votes = [results[s]["verdicts"][a["id"]] for s in SIZES if a["id"] in results[s]["verdicts"]]
            mine = results[size]["verdicts"].get(a["id"])
            if mine is None or len(votes) < 2:
                continue
            majority = Counter(votes).most_common(1)[0][0]
            total += 1
            agree += int(mine == majority)
        st = results[size]["stats"]
        n_verdicts = len(results[size]["verdicts"])
        rows.append({
            **st,
            "passed": sum(results[size]["verdicts"].values()),
            "pass_rate_pct": round(100 * sum(results[size]["verdicts"].values()) / n_verdicts, 1) if n_verdicts else None,
            "agreement_with_majority_pct": round(100 * agree / total, 1) if total else None,
        })

    out = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "model": state["metrics"]["model"],
        "candidates": len(candidates),
        "rows": rows,
        "per_article": [
            {"id": a["id"], "title": a["title"], "source": a["source_id"],
             **{f"b{s}": results[s]["verdicts"].get(a["id"]) for s in SIZES}}
            for a in candidates
        ],
    }
    (ROOT / "store").mkdir(exist_ok=True)
    (ROOT / "store" / "batch_experiment.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n| batch_size | LLM 호출 | 소요(초) | 판정 누락 | 통과율 | 다수결 일치율 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['batch_size']} | {r['calls']} | {r['seconds']} | {r['missing']}건 ({r['missing_rate_pct']}%) | "
              f"{r['pass_rate_pct']}% | {r['agreement_with_majority_pct']}% |")


if __name__ == "__main__":
    main()
