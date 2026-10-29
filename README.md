# 🐣 바이브삐약 오픈소스 모닝 브리핑

AI 에이전트·바이브코딩 **입문자**를 위해 매일 아침 08:00(KST) GitHub Trending · GeekNews · Show HN 에서 "오늘 바로 써 볼 만한" 오픈소스 3~5개를 골라
**3줄 요약 + 입문 난이도 + 실전 팁**으로 디스코드에 배달하는 LangGraph 뉴스레터 에이전트입니다. 봇 이름은 `🐣 코딩삐약이`.

> 모두의연구소 AI에이전트 2기 「뉴스레터 에이전트 만들기 [프로젝트]」 제출물 — 과제 보고서는 **[REPORT.md](REPORT.md)**

```
수집(3곳, 금지 6곳 차단) → 예선(규칙 + 10건 묶음 LLM) → 본선(3축 가중 채점, Top 3~5)
→ README 본문 요약 + 입문자 인사이트 → 검수(숫자 대조 + LLM 원문 대조, 재생성 ≤2회, 실패 시 스킵)
→ 디스코드 발행 + output/ · store/metrics.jsonl
```

## 문서

| 문서 | 내용 |
|---|---|
| [REPORT.md](REPORT.md) | 과제 6항목 — 분야·독자 / 소스 채택표 / 선별 로직 / 구조도 / 실행 기록 / 회고 |
| [PRD.md](PRD.md) | 무엇을 · 누구를 위해 · 통과 기준 |
| [TECH_SPEC.md](TECH_SPEC.md) | 스택 · 설정 · 상태 · LLM 호출 · 실패 처리 · 초안 대비 변경 |
| [DESIGN.md](DESIGN.md) | 노드별 설계 판단과 상태 흐름 |
| [작업기록.md](작업기록.md) | 막히고 고친 순서 |

## 실행

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env   # GEMINI_API_KEY, DISCORD_WEBHOOK_URL 채우기
python run.py --dry-run   # 디스코드로 보내지 않고 output/ 만 만든다
python run.py --send      # 디스코드 발송
```

검증 도구 (`tools/`): `measure_sources.py`(소스 실측) · `batch_experiment.py`(예선 묶음 크기 비교) · `robustness_checks.py`(금지 소스 · 깨진 소스 · 틀린 요약).

## 자동 발행 (GitHub Actions)

`.github/workflows/newsletter.yml` — 매일 23:00 UTC(= 08:00 KST) + Actions 탭의 **Run workflow** 버튼.
저장소 **Settings ▸ Secrets and variables ▸ Actions** 에 `GEMINI_API_KEY`, `DISCORD_WEBHOOK_URL` 을 넣으면 동작하고,
실행이 끝나면 `output/` 과 `store/` 를 봇이 커밋해 실행 기록이 저장소에 쌓입니다.

## 구조

```
graph.py   run.py   audience.yaml   requirements.txt
store/metrics.jsonl   store/published_history.json   output/newsletter_YYYY-MM-DD.{md,html}
tools/   screenshots/   .github/workflows/newsletter.yml
```
