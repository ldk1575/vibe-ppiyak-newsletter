"""
run.py - 나만의 뉴스레터 에이전트 (🐣 바이브삐약 오픈소스) 실행 엔트리포인트
실행 방법:
  1) .env 파일 또는 환경변수 설정 (.env 는 커밋하지 않는다, Actions 에서는 Secrets):
     GEMINI_API_KEY=...
     DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
     DRY_RUN=1            # 1 이면 디스코드로 보내지 않고 파일만 만든다
  2) 실행:
     python run.py              # .env 의 DRY_RUN 을 따른다
     python run.py --dry-run    # 강제로 보내지 않음
     python run.py --send       # 강제로 디스코드 발송
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description="🐣 바이브삐약 오픈소스 뉴스레터 에이전트")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="디스코드로 보내지 않는다")
    group.add_argument("--send", action="store_true", help="디스코드로 보낸다")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔에서 이모지·한글 깨짐 방지

    load_dotenv()
    if args.dry_run:
        os.environ["DRY_RUN"] = "1"
    elif args.send:
        os.environ["DRY_RUN"] = "0"
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("❌ GEMINI_API_KEY 가 없습니다. .env 또는 Actions Secrets 를 확인하세요.")
        return 2

    from graph import ROOT, build_newsletter_graph

    print("🐣 [바이브삐약 오픈소스] 코딩삐약이 뉴스레터 에이전트 파이프라인을 시작합니다...")
    print(f"  - 모드: {'dry-run (발송 안 함)' if os.getenv('DRY_RUN') == '1' else '디스코드 발송'}")

    app = build_newsletter_graph()
    try:
        # 재생성 루프는 max_retries 로 끝나지만, 설정 실수로 무한히 돌지 않게 상한을 한 번 더 건다
        final_state = app.invoke({}, config={"recursion_limit": 30})
    except Exception as e:
        # 노드 안의 실패는 노드가 처리한다. 여기까지 올라온 것은 설정 오류(금지 소스 등)나 예상 못 한 버그다.
        (ROOT / "store").mkdir(exist_ok=True)
        with open(ROOT / "store" / "metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "run_id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
                "trigger": os.getenv("RUN_TRIGGER", "local"),
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }, ensure_ascii=False) + "\n")
        traceback.print_exc()
        print(f"\n❌ 파이프라인 중단: {type(e).__name__}: {e}")
        return 1

    m = final_state["metrics"]
    funnel = m["funnel"]
    print("\n✅ 파이프라인 실행 완료! 삐약!")
    print(f"  - 1단계 소스별 수집        : {m['source_counts']}")
    if m["source_errors"]:
        print(f"  - 1단계 소스 오류          : {m['source_errors']}")
    print(f"  - 1단계 총 수집 건수       : {funnel['collected_total']}건")
    print(f"  - 2-A단계 규칙 탈락/예선 통과: {funnel['prelim_rule_dropped']}건 / {funnel['prelim_passed']}건")
    print(f"  - 2-B단계 본선 채점/선발   : {funnel['final_scored']}건 / {funnel['final_selected']}건")
    print(f"  - 4단계 검수 통과/재시도/스킵: {funnel['eval_passed']}건 / {funnel['eval_retried']}회 / {funnel['eval_skipped']}건")
    print(f"  - 5단계 최종 발행          : {funnel['published']}건")
    print(f"  - 5단계 로컬 저장 파일     : {final_state['published_files']}")
    print(f"  - 5단계 디스코드 발송      : {final_state['webhook_sent']}")
    print(f"  - LLM 호출                 : {m['llm_stats']}")
    print(f"  - 노드별 소요(초)          : {m['node_seconds']}")
    print("  - 실행 메트릭 로그 저장    : store/metrics.jsonl")

    # Actions 에서 '발행 0건'은 실패가 아니지만, 디스코드 발송 실패는 실패로 표시한다
    sent = final_state["webhook_sent"]
    if os.getenv("DRY_RUN") != "1" and not sent.get("discord"):
        print("❌ 디스코드 발송에 실패했습니다.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
