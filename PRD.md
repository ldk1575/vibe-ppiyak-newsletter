# PRD — 🐣 바이브삐약 오픈소스 모닝 브리핑 (나만의 뉴스레터 에이전트)

> 작성 2026-10-29 · 과제: 모두의연구소 AI에이전트 2기 「에이전트 팀 꾸리기_Agt1 · 3. 뉴스레터 에이전트 만들기 [프로젝트]」
> 기준 설계: 제미나이(Argon)로 만든 LangGraph 파이프라인 Mermaid 도식 + 초안 코드(`graph.py` · `run.py` · `audience.yaml` · `report.md`)
> 제출: 공개 깃허브 저장소 URL (`ldk1575/vibe-ppiyak-newsletter`) — **제출 후 수정 불가**

---

## 1. Executive Summary

- **문제** — AI 에이전트·바이브코딩 입문자는 매일 쏟아지는 오픈소스 중 "오늘 바로 깔아 볼 만한 것"을 고르지 못하고, 영문 README만 봐서는 내 실습에 어떻게 붙일지 감이 오지 않는다.
- **해결** — 금지 소스 6곳을 뺀 3개 채널(GitHub Trending · GeekNews · Show HN)에서 매일 08:00 KST에 자동 수집 → 2단계 선별(예선 배치 / 본선 가중치 채점) → README 본문 기반 요약 + 입문자 인사이트 → 원문 대조 검수(실패 시 재생성 최대 2회, 그래도 실패면 스킵) → **디스코드 발행**까지 GitHub Actions가 돌린다.
- **성공 기준 (KPI)**
  1. GitHub Actions 한 번 실행으로 수집~디스코드 발행이 **오류 없이 끝난다** (워크플로 ✅, 디스코드 메시지 1건).
  2. 매 실행마다 최종 발행 **3~5건** (후보가 부족한 날은 그 사실이 metrics에 남는다).
  3. 발행된 모든 기사가 **검수 `pass`** 상태이고, 요약·인사이트에 원문에 없는 숫자가 0개다.
  4. `store/metrics.jsonl`에 실행마다 **1줄**이 쌓이고, 모든 후보 기사의 예선/본선 판정 사유가 들어 있다.
  5. 같은 저장소 URL이 7일 안에 **두 번 발행되지 않는다**.

## 2. User Experience & Functionality

### 페르소나

- **병아리 빌더** — Claude Code · Cursor · Codex · MCP에 막 입문한 주니어 개발자 · 학원 수강생 · 1인 빌더. 영어 README가 부담스럽고 "설치 5분 안에 되는가"가 제일 궁금하다.
- **운영자(나)** — 매일 손대지 않고 돌아가길 원하고, 결과가 이상하면 metrics만 보고 어느 단계가 틀렸는지 알고 싶다.

### 사용자 스토리와 인수 기준

| # | 스토리 | 인수 기준 (눈으로 확인) |
|---|---|---|
| S1 | 독자로서, 매일 아침 디스코드 채널에서 3~5개 오픈소스 카드를 받고 싶다 | 디스코드 `news_agent` 채널에 봇 이름 `🐣 코딩삐약이`로 메시지 1건 + embed 3~5개가 도착한다 |
| S2 | 독자로서, 카드마다 "무엇인지 / 입문 난이도 / 오늘 써 볼 방법"을 한국어로 보고 싶다 | embed마다 3줄 요약 · 난이도(🐣/🐥/🐓) · 실전 팁 칸과 원문 링크가 있다 |
| S3 | 독자로서, 지어낸 기능·스타 수가 없는 믿을 수 있는 요약을 원한다 | 발행 기사 전부 `eval_status=pass`, 요약·인사이트의 숫자가 모두 원문에 있다 |
| S4 | 운영자로서, 사람 손 없이 매일 돌게 하고 싶다 | Actions가 cron(UTC 23:00 = KST 08:00)과 수동 버튼 둘 다로 실행되고, 끝나면 `output/` · `store/`를 저장소에 커밋한다 |
| S5 | 운영자로서, 한 기사·한 소스가 실패해도 나머지는 발행되길 원한다 | 소스 하나를 일부러 깨뜨려도(잘못된 URL) 나머지로 발행되고, metrics에 그 소스 오류가 기록된다 |
| S6 | 운영자로서, 왜 이 기사가 뽑혔는지 로그로 증명하고 싶다 | metrics에 전 후보의 예선 통과/탈락 사유, 본선 3축 점수·가중합·근거, 검수 피드백이 있다 |
| S7 | 운영자로서, 금지 소스가 섞이면 즉시 막히길 원한다 | `audience.yaml`에 금지 URL을 채택 소스로 넣으면 수집 단계에서 실행이 거부된다 |
| S8 | 독자로서, 오늘 GitHub에서 뜨는 저장소들이 **스타 기준 몇 위인지** 한눈에 보고 싶다 | 뉴스레터 맨 아래(디스코드 마지막 embed · MD/HTML 표)에 🏆 오늘의 트렌딩 TOP 10이 누적 스타 순으로 있고, 숫자는 GitHub API 값과 같다 |

### 비목표 (Non-Goals)

- Slack 발행 — 초안에는 있었지만 **디스코드만** 한다 (코드에서 제거).
- 이메일 구독 · 구독자 관리 · 웹 화면 — 발행 채널은 디스코드와 저장소 안 MD/HTML 파일뿐.
- 독자 이모지 반응을 가중치에 반영하는 학습 루프 — 회고의 개선점으로만 남긴다.
- 유료 모델 · 벡터DB · 별도 서버.

## 3. AI System Requirements

### 도구·API

- **LLM**: Google Gemini (`GEMINI_API_KEY`, 기본 모델 `gemini-flash-latest`, 환경변수로 교체 가능). 초안의 OpenAI는 키가 없어 Gemini로 바꾼다 — 어제 실습과 같은 키.
- **LangGraph** `StateGraph` + **LangChain** 구조화 출력(Pydantic).
- **RSS**: `feedparser` + `requests` · **본문 추출**: `BeautifulSoup`(GitHub README `article.markdown-body` 우선).
- **발행**: 디스코드 웹훅(`DISCORD_WEBHOOK_URL`).
- **자동화**: GitHub Actions (cron + `workflow_dispatch`), 비밀값은 Actions Secrets.

### LLM 호출 단계

| 단계 | 호출 단위 | 출력 |
|---|---|---|
| 예선 | 10건 묶음 1회 | 기사별 통과 여부 + 사유 |
| 본선 | 10건 묶음 1회 (초안의 1건 1회에서 변경) | 3축 점수 + 근거 |
| 요약 | 선발 기사 1건 1회 | 3줄 요약 · 인사이트 · 난이도 |
| 검수 | 기사 1건 1회 | pass/fail + 수정 지시 |
| 재생성 | retry 기사 1건 1회 | 요약 다시 쓰기 |

### 평가 전략

- **규칙 검수(결정적)**: 요약·인사이트에 나온 숫자가 원문(full_text)에 없으면 실패. 원문 URL이 보존됐는지 확인.
- **LLM 검수**: `audience.yaml`의 `evaluation_and_retry.checks` 세 문장을 그대로 기준으로 원문 대조.
- **일부러 틀린 요약 테스트**: 원문 숫자를 바꾼 요약을 넣으면 검수가 `fail`을 내는지 확인한다.
- **배치 크기 실험**: 같은 후보로 batch 5 / 10 / 30을 돌려 호출 수 · 시간 · 판정 누락률을 재고 그 숫자로 `batch_size`를 정한다.

## 4. Technical Specifications

### 아키텍처

```
START → load_config → collect_rss → rank_github_stars → filter_prelim → filter_final
      → fetch_and_summarize → evaluate_summary ─┬─(retry 있음)→ regenerate_summary → evaluate_summary
                                                └─(전부 pass/skip)→ publish → END
```
세부는 `TECH_SPEC.md`, 노드별 입출력과 예외 경로는 `DESIGN.md`.

### 저장/데이터 설계

| 파일 | 내용 | 누가 쓰나 |
|---|---|---|
| `audience.yaml` | 독자 · 소스(채택/금지) · 선별 기준 · 검수 기준 · 발행 설정 | 사람 |
| `store/metrics.jsonl` | 실행 1회 = 1줄. 소스별 수집 수, 퍼널, 전 후보 선별 로그, 검수 로그, 발행 결과 | 파이프라인 (append) |
| `store/published_history.json` | 발행한 URL과 날짜 (7일 중복 방지) | 파이프라인 |
| `output/newsletter_YYYY-MM-DD.{md,html}` | 그날 뉴스레터 | 파이프라인 |
| `.env` (커밋 안 함) / Actions Secrets | `GEMINI_API_KEY`, `DISCORD_WEBHOOK_URL` | 사람 |

### 보안 · 개인정보

- 키와 웹훅 주소는 **저장소에 절대 커밋하지 않는다** — `.gitignore`에 `.env`, push 전에 비밀값 문자열 검색.
- 웹훅 주소는 주소 자체가 열쇠라 로그·metrics에도 남기지 않는다.
- 수집 대상은 공개 RSS와 공개 README뿐, 개인정보 없음.

## 5. 내가 넣고 싶은 기능 (초안 대비 추가)

1. **GitHub Actions 매일 자동 발행 + 결과 자동 커밋** — 저장소 자체가 실행 기록 보관소가 된다.
2. **7일 중복 발행 방지** — GitHub Trending은 같은 저장소가 며칠 연속 뜨므로.
3. **숫자 대조 규칙 검수** — LLM 검수 앞에 0원짜리 결정적 검사를 둔다.
4. **소스 실측 스크립트** — 소스 채택표의 숫자를 지어내지 않고 실제로 잰다.
5. **🏆 GitHub 트렌딩 스타 순위 TOP 10** (2026-10-29 사용자 요청) — 오늘 트렌딩 저장소를 GitHub REST API의 누적 스타 수로 1~10위. 큐레이션(선별·요약·검수)과 별개인 사실 표라 LLM을 거치지 않는다.

## 6. 규칙

- 금지 소스 6곳(OpenAI · DeepMind · TechCrunch · The Verge · MIT TR · AI타임스)은 수집 단계에서 하드 차단.
- 소스는 3곳 이상, 최종 발행은 3~5건.
- 한 소스 · 한 기사 · 한 LLM 호출이 실패해도 **파이프라인은 멈추지 않는다** (실패는 metrics에 기록).
- 재생성은 최대 2회, 그래도 실패면 스킵. 그래프 루프에 `recursion_limit`.
- REPORT.md의 수치는 **실제로 잰 값만** 쓴다. 초안 report.md의 수치(수집량 · 노이즈 비율 · 배치 실험 결과)는 측정 전이라 전부 다시 잰다.

## 7. 통과 기준 (구현 뒤 실제로 확인하고 결과를 기록)

- [ ] 로컬에서 `python run.py`(DRY_RUN=1)가 오류 없이 끝나고 `output/`에 MD·HTML이 생긴다
- [ ] 같은 실행의 metrics.jsonl 한 줄에 소스 3곳 각각의 수집 건수가 0보다 크다
- [ ] 최종 발행 3~5건, 전부 `eval_status=pass`
- [ ] 일부러 숫자를 바꾼 요약이 검수에서 떨어진다
- [ ] 금지 URL을 채택 소스에 넣으면 실행이 거부된다
- [ ] 잘못된 소스 URL 하나가 섞여도 나머지로 발행된다
- [ ] 두 번째 실행에서 첫 실행에 발행한 URL이 다시 뽑히지 않는다
- [ ] GitHub Actions 수동 실행이 ✅로 끝나고 디스코드 채널에 메시지가 도착한다
- [ ] Actions가 `output/` · `store/` 변경을 저장소에 커밋한다
- [ ] 공개 저장소 어디에도 키·웹훅 주소가 없다 (검색 결과 0건)
- [ ] REPORT.md 6항목(분야·독자 / 소스 채택표 / 선별 로직 / 구조도 / 실행 기록 캡처 / 회고)이 모두 채워져 있다
- [ ] 디스코드 메시지와 MD·HTML에 스타 순위 TOP 10이 있고, 1위의 스타 수가 같은 시각 GitHub API 값과 같다

## 8. Risks & Roadmap

| 위험 | 대응 |
|---|---|
| Gemini 무료 한도(분당 호출 수) 초과 → 429 | 본선을 배치로 바꿔 호출 수 절감, 레이트 리미터 + 재시도 |
| RSS 하나가 죽음 / 형식 변경 | 소스별 try/except, backup_url, 다른 소스로 발행 계속 |
| GitHub README 크롤링 실패 | RSS 요약으로 대체, 너무 짧으면 해당 기사 요약 품질 경고 |
| 검수 오탐(정상 요약을 떨어뜨림) | 숫자 정규화(쉼표·단위), 재생성 피드백에 걸린 숫자를 명시 |
| 후보가 3건 미만인 날 | min_score 미달이어도 상위 3건까지 채우고 그 사실을 metrics에 기록 |
| Actions의 커밋 충돌 | 워크플로 동시 실행 금지(`concurrency`), 커밋 전 `git pull --rebase` |

- **MVP(오늘)** — 5단계 파이프라인 + 디스코드 + Actions + metrics + 중복 방지 + REPORT.
- **v1.1** — 독자 이모지 반응 수집, 주간 다이제스트.
- **v2.0** — 반응 기반 가중치 자동 조정, 소스 자동 탐색.

## 변경 기록

- 2026-10-29 최초 작성.
- 2026-10-29 구현 중 변경 (이유는 TECH_SPEC.md 10절 표)
  - **스타 순위 TOP 10 추가** — 사용자 요청. 새 노드 `rank_github_stars`(수집 직후), Actions 에 `GITHUB_TOKEN` 주입.
  - **GeekNews 페이지는 크롤링하지 않는다** — 봇 요청에 403. 브라우저로 위장하지 않고 RSS 미리보기(160~200자)만으로 요약하고, 그런 기사에는 "📎 원문 미리보기 기반 요약" 표시를 단다. 주 URL도 feedburner → 공식 RSS 로.
  - **제외 키워드에서 `token` 제거, 영문은 단어 경계 매칭** — `token` 은 LLM 글에 흔하고 `crypto` 가 `cryptography` 에 걸렸다.
  - **72시간 신선도 필터 추가** — 실측에서 Show HN(points≥20) 글의 48시간 이내 비율이 20%뿐이었다.
  - **본선도 묶음 채점, `min_k`·`max_per_source` 추가** — 무료 한도 대비 호출 수 절감, 3~5건 보장, 한 소스 독식 방지.
