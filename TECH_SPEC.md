# TECH_SPEC — 🐣 바이브삐약 오픈소스 모닝 브리핑

> 무엇을 만드는지는 `PRD.md`, 노드별 설계 판단은 `DESIGN.md`, 결과와 근거 수치는 `REPORT.md`.
> 이 문서는 **어떻게 돌아가는지** — 스택 · 설정 · 상태 · 외부 연동 · 실패 처리 · 기록 형식.

## 1. 스택

| 구분 | 선택 | 버전(검증한 것) | 이유 |
|---|---|---|---|
| 언어 | Python | 3.12 (로컬 · Actions 동일) | 어제 실습 환경과 같음 |
| 오케스트레이션 | LangGraph `StateGraph` | 1.2.18 | 조건부 엣지로 검수→재생성 루프 표현 |
| 프롬프트 · 구조화 출력 | LangChain Core + Pydantic | 1.7.1 / 2.14 | `with_structured_output` 로 JSON 파싱 실패 제거 |
| LLM | Gemini (`langchain-google-genai`) | 4.4.2, 모델 `gemini-flash-latest`(실행 당일 `gemini-3.8-flash`로 해석됨) | 보유 키가 Gemini. 초안의 OpenAI 는 키 없음 |
| 수집 | `requests` + `feedparser` | 2.32 / 6.0.14 | 타임아웃 · UA 지정 후 파싱 |
| 본문 추출 | `BeautifulSoup` | 4.12 | GitHub README `article.markdown-body` 직접 선택 |
| 발행 | Discord Webhook | API v10 | 사용자 채널 `news_agent` |
| 자동화 | GitHub Actions | `ubuntu-latest` | cron + 수동 실행 + 결과 커밋 |

## 2. 디렉토리

```
vibe-ppiyak-newsletter/
├── graph.py                  # LangGraph 메인 로직 (노드 9개 + 빌더)
├── run.py                    # 실행 엔트리포인트 (--dry-run / --send)
├── audience.yaml             # 독자 · 소스 · 선별 · 검수 · 발행 설정 (코드는 이것만 읽는다)
├── requirements.txt
├── .github/workflows/newsletter.yml
├── tools/
│   ├── measure_sources.py    # 소스 후보 실측 → store/source_measurement.json
│   ├── batch_experiment.py   # 예선 batch 5/10/30 비교 → store/batch_experiment.json
│   └── robustness_checks.py  # 금지 소스 · 깨진 소스 · 틀린 요약 검사 → store/robustness_checks.json
├── store/
│   ├── metrics.jsonl         # 실행 1회 = 1줄 (append)
│   └── published_history.json
├── output/newsletter_YYYY-MM-DD.{md,html}
├── screenshots/              # REPORT 실행 기록 캡처
├── PRD.md · TECH_SPEC.md · DESIGN.md · REPORT.md · 작업기록.md · README.md
└── .env (커밋 안 함)
```

## 3. 환경 변수

| 이름 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅ | — | `GOOGLE_API_KEY` 도 인식 |
| `DISCORD_WEBHOOK_URL` | 발송 시 | — | 주소 자체가 비밀. 로그 · metrics 에 남기지 않음 |
| `DRY_RUN` | | `0` | `1` 이면 디스코드 생략 (파일 · metrics 는 생성) |
| `GEMINI_MODEL` | | `gemini-flash-latest` | |
| `GEMINI_THINKING_LEVEL` | | `low` | 분류 · 채점 · 요약용 |
| `EVAL_THINKING_LEVEL` | | `medium` | 검수용 (원문 대조) |
| `LLM_REQUESTS_PER_SECOND` | | `0.15` | 분당 9회. 무료 한도 아래로 |
| `RUN_TRIGGER` | | `local` | Actions 에서 `schedule` / `workflow_dispatch` |
| `AUDIENCE_CONFIG` | | `./audience.yaml` | 다른 독자 설정으로 돌릴 때 |
| `GITHUB_TOKEN` | | — | 스타 순위용 GitHub API. 없으면 시간당 60회(트렌딩 11~25개라 충분), Actions 는 자동 토큰으로 1000회 |

## 4. 설정 스키마 (`audience.yaml`)

| 키 | 쓰는 노드 | 내용 |
|---|---|---|
| `newsletter.*` | publish | 이름 · 봇 이름 |
| `audience.persona / desired_tone` | prelim · summarize · regenerate | 프롬프트에 주입 |
| `sources.excluded_urls / excluded_domains` | collect | 금지 6곳. URL 정규화 + 도메인 접미사 매칭 |
| `sources.adopted[]` | collect | `id, name, url, backup_url` |
| `sources.max_items_per_source / max_age_hours` | collect | 25건 / 72시간 |
| `github_ranking.*` | rank_github_stars · publish | `enabled, source_id, extra_feeds, top_n(10), sort_by(stargazers_count)` |
| `selection_criteria.importance_question` | prelim · final | 중요도 판단 핵심 문장 |
| `selection_criteria.preliminary.*` | prelim | `batch_size`, `dedup_days`, 포함 · 제외 키워드 |
| `selection_criteria.final_scoring.*` | final | `batch_size, top_k, min_k, min_score, max_per_source, weights, rubric_prompt` |
| `summarize.max_body_chars / min_body_chars` | summarize | 6000 / 300 |
| `evaluation_and_retry.max_retries / checks` | evaluate | 2회 / 검수 기준 3문장 (프롬프트에 그대로) |
| `publishing.output_dir / store_dir` | publish | |

## 5. 상태 (`NewsletterState`)

| 키 | 타입 | 채우는 노드 |
|---|---|---|
| `run_id` | `YYYYMMDD_HHMMSS` (KST) | load_config |
| `audience_config` | dict | load_config |
| `raw_articles` | `ArticleItem[]` | collect |
| `prelim_articles` | `ArticleItem[]` | prelim |
| `selected_articles` | `ArticleItem[]` (3~5) | final → summarize → evaluate ⇄ regenerate |
| `final_articles` | `eval_status == pass` 만 | publish |
| `trending_repos` | `{full_name, url}[]` 트렌딩 전체 | collect |
| `github_ranking` | `{rank, full_name, url, stars, forks, language, description, trending_feed}[]` ≤10 | rank_github_stars |
| `metrics` | dict (7절) | 모든 노드 |
| `published_files` · `webhook_sent` | dict | publish |

`ArticleItem` 핵심 필드: `id`(URL md5 8자) · `url`(끝 `/` 제거) · `source_id` · `raw_summary`(RSS, 800자) · `full_text`(본문) · `body_source`(`readme|page|rss_fallback`) · `prelim_passed/reason` · `score` · `score_breakdown` · `score_reason` · `summary` · `beginner_insight` · `difficulty_stars` · `eval_status`(`pending|pass|retry|skip`) · `eval_feedback` · `retry_count`.

## 6. LLM 호출 명세

모든 호출은 `call_llm(stage, chain, inputs)` 한 곳을 지나며 단계별 횟수 · 오류가 `metrics.llm_stats` 에 남는다. 레이트 리미터는 프로세스 전체에서 하나를 공유하고, 429 등은 SDK `max_retries=6` 지수 백오프.

| stage | 입력 | 출력 스키마 | 호출 수 (후보 N, 선발 K) | 실패 시 |
|---|---|---|---|---|
| `prelim` | 묶음 JSON(id·제목·출처·URL·요약 250자) | `PrelimBatchOutput{decisions[id,passed,reason]}` | ⌈N/10⌉ | 그 묶음은 키워드 대체 판정 (`decided_by=keyword_fallback`) |
| `final` | 묶음 JSON(요약 500자) | `FinalScoreBatch{scores[id,3축,reason]}` | ⌈M/10⌉ + 누락분 1회 | 누락 기사 0점 |
| `summarize` | 본문 ≤6000자 | `SummaryInsightOutput{summary,beginner_insight,difficulty_stars}` | K | 그 기사 `skip` |
| `evaluate` | 원문 + 요약 + 인사이트 + yaml checks | `EvaluationOutput{passed,feedback}` | 규칙 통과분만 | 불통과로 간주 → retry/skip |
| `regenerate` | 원문 + 이전 요약 + 지적사항 | `SummaryInsightOutput` | retry 건수 | 이전 요약으로 재검수 (횟수는 증가) |

최악의 경우 호출 수 = ⌈N/10⌉ + ⌈M/10⌉·2 + K + K·(1+max_retries)·2 — 후보 60 · 선발 4 기준 약 36회, 분당 9회로 4분 안쪽.

## 7. 기록 형식 (`store/metrics.jsonl` 한 줄)

```jsonc
{
  "run_id": "20261029_160501", "timestamp": "...+09:00", "trigger": "workflow_dispatch",
  "model": "gemini-flash-latest", "dry_run": false,
  "source_counts": {"github_trending": 11, "geeknews": 25, "hackernews_show": 6, "hackernews_show_too_old_dropped": 14},
  "source_errors": {},
  "funnel": {"collected_total": 42, "prelim_rule_dropped": 1, "prelim_passed": 15, "final_scored": 15,
             "final_selected": 4, "eval_passed": 4, "eval_retried": 1, "eval_skipped": 0, "published": 4},
  "prelim_batch_stats": {"batch_size": 10, "calls": 5, "missing": 0, "missing_rate_pct": 0.0, "seconds": 31.2},
  "selection_logs": [ {"stage": "prelim_rule|prelim_batch|final_scoring", "id": "...", "passed|score": ..., "reason": "..."} ],
  "evaluation_logs": [ {"id": "...", "retry_count": 0, "check": "rule_numbers|llm|llm_error|summarize", "eval_status": "retry", "feedback": "..."} ],
  "body_sources": {"<id>": {"source": "readme", "chars": 6000}},
  "published_files": {"markdown": "output/newsletter_2026-10-29.md", "html": "..."},
  "webhook_sent": {"discord": true, "status": 200, "message_id": "...", "embeds": 4},
  "published_articles": [ {"id": "...", "url": "...", "score": 0.86, "retry_count": 1, "body_source": "readme"} ],
  "llm_stats": {"calls": 17, "errors": 0, "by_stage": {"prelim": 5, "final": 2, "summarize": 4, "evaluate": 5, "regenerate": 1}},
  "node_seconds": {"collect_rss": 3.1, "...": 0}
}
```
(위 숫자는 형식 예시다. 실제 값은 REPORT.md 5절.) 노드 밖으로 예외가 새면 `run.py` 가 `{"status":"failed","error":...}` 한 줄을 남기고 종료 코드 1.

## 8. 외부 연동

### GitHub REST API (스타 순위)
- `GET https://api.github.com/repos/{owner}/{repo}` (`Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, 토큰 있으면 `Authorization: Bearer`).
- 쓰는 필드: `full_name, html_url, stargazers_count, forks_count, language, description`. 조회 시각을 `metrics.github_ranking.fetched_at` 에 남기고 발행물에 "몇 시 기준"으로 적는다 (스타는 계속 변하므로).

### 디스코드 웹훅
- `POST {webhook}?wait=true` → 200 + 메시지 JSON(`id` 를 metrics 에 기록). 429 면 `retry_after` 만큼 대기 후 최대 3회.
- 한도 지키기: `content` ≤ 2000자, embed ≤ 10개, 제목 ≤ 256자, 필드 값 ≤ 1024자, embed 합계 ≤ 6000자(5800에서 자름).
- 발행 0건인 날은 "오늘은 쉬어 갈게요" 텍스트 메시지 1건.

### GitHub Actions (`.github/workflows/newsletter.yml`)
- 트리거: `schedule: "0 23 * * *"`(KST 08:00) + `workflow_dispatch(dry_run)`.
- Secrets: `GEMINI_API_KEY`, `DISCORD_WEBHOOK_URL`. `permissions: contents: write`.
- `concurrency: newsletter` 로 겹침 방지, 실행 후 `output/` · `store/` 를 봇 이름으로 커밋(`if: always()` — 실패 기록도 남김), push 전 `pull --rebase`.
- `run.py` 종료 코드: 디스코드 발송 실패면 1 → 워크플로 ❌. 발행 0건은 실패가 아님(채널에 안내 메시지).

## 9. 실패 처리 매트릭스

| 실패 | 위치 | 처리 | 남는 기록 |
|---|---|---|---|
| 금지 소스가 설정에 있음 | collect 시작 전 | **실행 거부** (ValueError) | metrics `status=failed` |
| 채택 소스 < 3 | collect 시작 전 | 실행 거부 | 동일 |
| RSS 5xx · 타임아웃 · 0건 | collect | backup_url → 그래도 실패면 그 소스 0건으로 계속 | `source_errors` |
| 오래된 글 | collect | 72시간 초과 제외 | `source_counts.<id>_too_old_dropped` |
| 예선 LLM 실패 · 판정 누락 | prelim | 키워드 대체 판정 | `decided_by=keyword_fallback`, `prelim_batch_stats.missing` |
| 본선 채점 누락 | final | 누락분 1회 재호출 → 0점 | `score_reason` |
| 기준 통과 < 3건 | final | 차점자로 3건 채움 | `selected_reason="하한 3건 채우기"` |
| 본문 크롤링 실패 · 300자 미만 | summarize | RSS 요약으로 대체 | `body_sources` |
| 요약 LLM 실패 | summarize | 그 기사 skip | `evaluation_logs.check=summarize` |
| 원문에 없는 숫자 | evaluate (규칙) | retry, 피드백에 숫자 명시 | `check=rule_numbers` |
| LLM 검수 불통과 · 호출 실패 | evaluate | retry → `max_retries` 초과 시 skip | `check=llm / llm_error` |
| 재생성 실패 | regenerate | 이전 요약으로 재검수 (횟수 증가 → 반드시 종료) | |
| 그래프 무한 루프 | run | `recursion_limit=30` | |
| 디스코드 실패 | publish | 3회 재시도, 이력 미기록, 종료 코드 1 | `webhook_sent.status` |

## 10. 초안(제미나이 Argon) 대비 변경

| # | 초안 | 변경 | 이유 |
|---|---|---|---|
| 1 | `ChatOpenAI(gpt-4o-mini)` | `ChatGoogleGenerativeAI(gemini-flash-latest)` + 레이트 리미터 + `thinking_level` | 보유 키가 Gemini. 무료 한도 대비. 기본 생각 모드는 짧은 답에도 생각 토큰 471개 · 6.2초, `low` 는 2.3초 |
| 2 | Slack + Discord | Discord 만 | 사용자 결정 (발행 채널은 디스코드) |
| 3 | 본선 기사 1건 = 호출 1회 | 10건 묶음 1회 | 후보 20건이면 20회 → 2회 |
| 4 | `min_score: 0.70` 정의만 하고 미사용 | 실제 적용 + `min_k` 하한 + `max_per_source` | 설정과 동작 불일치 해소, 3~5건 보장 |
| 5 | 백업 소스도 실패하면 예외로 전체 중단 | 소스별 격리 | 루브릭 "서비스 중단 없이" |
| 6 | 요약 · 검수 · 재생성 호출에 예외 처리 없음 | 기사 단위 격리 | 한 건 실패가 전체를 멈추던 것 |
| 7 | 검수 프롬프트가 yaml `checks` 를 안 읽음 | `checks` 를 그대로 주입 | 기준을 코드 밖으로 |
| 8 | LLM 검수만 | 숫자 대조 규칙 검수를 앞에 | 0원 · 결정적. 어제 7강의 숫자 대조 |
| 9 | 제외 키워드 부분 일치 (`token`, `crypto`) | 영문은 단어 경계, `token` 제거 | `token` 은 LLM 글에 흔하고, `crypto` 가 `cryptography` 에 걸림 |
| 10 | HTML 에 제목 · 요약을 그대로 삽입 | `html.escape` | 외부 문자열로 마크업이 깨지거나 스크립트가 들어가는 것 방지 |
| 11 | 날짜 `date.today()` | KST 고정 | Actions 러너가 UTC 라 08:00 실행이 전날 날짜로 찍힘 |
| 12 | `Path("audience.yaml")` 상대경로 | 파일 기준 절대경로 | 다른 폴더에서 실행해도 동작 |
| 13 | 중복 발행 방지 없음 (회고 개선점) | `published_history.json` 7일 | 매일 실행하면 Trending 저장소가 연달아 뜸 |
| 14 | 발행 날짜만 | 72시간 신선도 필터 | 측정 결과 Show HN(points≥20)은 48시간 이내 글이 20%뿐 |
| 15 | GeekNews feedburner 주 · 백업 없음 | 공식 RSS 주 · feedburner 백업 | 같은 50건, 응답 0.18초 vs 1.18초 |
| 16 | report.md 수치(수집량 · 노이즈율 · 배치 실험) | 실측값으로 교체 | 초안 수치는 측정 근거가 없음 |
| 17 | 없음 | 🏆 GitHub 트렌딩 스타 순위 TOP 10 (`rank_github_stars` 노드) | 사용자 요청. RSS 에 스타 수가 없어 GitHub REST API 사용 |
| 18 | GeekNews 링크도 크롤링 | `no_fetch_domains` 로 요청 안 함, RSS 본문 + "미리보기 기반" 표시 | 토픽 페이지가 봇 요청에 403. 위장 우회는 하지 않음 |
| 19 | 검수관에 난이도 미전달 | 난이도 · 본문 출처를 검수 입력에 추가 | 첫 실행에서 "난이도 표기 누락"으로 정상 요약이 반려됨 |
