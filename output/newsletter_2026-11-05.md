# 🐣 바이브삐약 오픈소스 모닝 브리핑 (2026-11-05)

> **큐레이터**: 🐣 코딩삐약이 | **타깃 독자**: AI 에이전트 입문자 · 바이브코딩 입문자
> **오늘의 선별 결과**: 총 53건 수집 → 예선 10건 통과 → 본선 3건 → 최종 3건 검수 완료 💌

## 1. [max-sixty/worktrunk](https://github.com/max-sixty/worktrunk)
- **출처**: GitHub Trending Daily | **중요도 점수**: `0.83` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: AI 코딩 에이전트 다중 작업 시 필수적인 Git worktree 관리를 쉽게 만들어 즉시 실무 바이브코딩에 적용하기 좋습니다.
- **검수**: 통과 (재생성 0회)

### 📌 3줄 핵심 요약
- Worktrunk는 Claude Code, Codex 등 여러 AI 에이전트를 동시에 실행할 때 서로의 코드가 꼬이지 않도록 Git worktree를 손쉽게 다룰 수 있게 해주는 CLI 도구입니다.
- 복잡했던 기존 git worktree 명령어 대신 브랜치 이름을 활용해 단일 명령어로 디렉터리 생성, 전환, 정리를 간결하게 처리합니다.
- 훅(Hooks) 자동화, diff 기반 LLM 커밋 메시지 생성, 빌드 캐시 공유(APFS, btrfs, XFS) 등 다중 병렬 작업을 위한 유용한 편의 기능을 지원합니다.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> 여러 AI 에이전트에게 동시에 다른 작업을 시키고 싶다면 `wt switch -c -x claude <브랜치명> -- '<작업 프롬프트>'` 명령어를 활용해 보세요! 새 작업 트리 생성과 Claude Code 실행이 한 번에 처리되어, 작업 디렉터리가 충돌할 걱정 없이 5~10개 이상의 작업을 안전하게 병렬로 돌려볼 수 있습니다.

## 2. [anomalyco/hex](https://github.com/anomalyco/hex)
- **출처**: GitHub Trending Daily | **중요도 점수**: `0.79` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: 로컬 음성 입력 도구로 설치가 간단하여 코딩 에이전트 프롬프트 음성 작성 워크플로우에 가볍게 쓰기 좋습니다.
- **검수**: 통과 (재생성 0회)

### 📌 3줄 핵심 요약
- Mac, Windows, Linux 환경을 지원하는 로컬 음성 받아쓰기(dictation) 도구입니다.
- 단축키를 누른 채 말하고 손을 떼면, 음성을 텍스트로 변환해 현재 열려 있는 앱에 바로 붙여넣어 줍니다.
- 첫 실행 시 음성 모델을 다운로드한 후에는 외부로 데이터가 전송되지 않고 기기 내부에서만 안전하게 동작합니다.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> 바이브코딩을 할 때 키보드로 길게 프롬프트를 치기 번거롭다면 Hex를 켜두고 단축키를 눌러 말해보세요! Cursor나 터미널의 에이전트 입력창에 음성으로 말한 내용이 텍스트로 즉시 붙여넣어지며, 로컬에서만 처리되어 프라이버시 걱정 없이 자연스럽게 아이디어를 전달할 수 있어요.

## 3. [Show HN: Codemap – one-page interactive map of any Go repository](https://github.com/peterretief/codemap)
- **출처**: Hacker News: Show HN (points>=20) | **중요도 점수**: `0.66` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: Go 저장소 구조를 한눈에 시각화해 에이전트가 코드를 탐색하거나 사람이 파악할 때 유용하지만 Go 언어에 한정되어 있습니다.
- **검수**: 통과 (재생성 0회)

### 📌 3줄 핵심 요약
- Go 모듈의 모든 패키지, 내부 의존 관계, 파일별 함수를 단일 HTML 파일로 인터랙티브하게 시각화해 주는 도구예요.
- 패키지 검색과 의존 관계 클릭 확인이 가능하며, GitHub 저장소의 경우 해당 함수 라인으로 바로 이동할 수 있어요.
- Go 1.24 이상 환경에서 명령어 한 줄(`go run github.com/peterretief/codemap@latest -o code-map.html`)로 실행하거나 GitHub Actions(`peterretief/codemap@v0.1.3`)로 자동 생성할 수 있어요.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> 낯선 오픈소스 Go 프로젝트나 바이브코딩으로 작성 중인 Go 저장소의 복잡한 구조를 단일 HTML 파일로 한눈에 파악할 수 있어요. 패키지 간의 연결 구조와 함수 위치를 브라우저에서 인터랙티브하게 확인하며 코드를 탐색해 보세요!

---

## 🏆 오늘의 GitHub 트렌딩 TOP 10 (⭐ 누적 스타 순)

> 오늘 GitHub Trending 에 오른 저장소를 GitHub API 의 누적 스타 수로 줄 세웠어요. 숫자는 2026-11-05 11:23 KST 기준.

| 순위 | 저장소 | ⭐ 스타 | 포크 | 언어 | 설명 |
|---:|---|---:|---:|---|---|
| 1 | [mattpocock/skills](https://github.com/mattpocock/skills) | 313,416 | 26,290 | Shell | Skills for Real Engineers. Straight from my .agents directory. |
| 2 | [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | 112,917 | 9,806 | TypeScript | Persistent Context Across Sessions for Every Agent –  Captures everything your … |
| 3 | [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) | 96,656 | 10,125 | Python | 🕷️ The BEST Web Scraping framework that handles everything from a single reques… |
| 4 | [JustVugg/colibri](https://github.com/JustVugg/colibri) | 47,784 | 5,536 | C | A hierarchical inference engine for frontier MoE models: hot experts on the GPU… |
| 5 | [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) | 46,826 | 7,717 | Python | Kronos: A Foundation Model for the Language of Financial Markets |
| 6 | [p-e-w/heretic](https://github.com/p-e-w/heretic) | 39,363 | 4,447 | Python | Training-free language model modification: Remove censorship, suppress slop, re… |
| 7 | [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | 35,445 | 4,695 | Shell | Turn Claude Code into a full game dev studio — 49 AI agents, 72 workflow skills… |
| 8 | [floci-io/floci](https://github.com/floci-io/floci) | 29,672 | 3,282 | Java | Light, fluffy, and always free - The AWS Local Emulator alternative |
| 9 | [Usagi-org/ai-goofish-monitor](https://github.com/Usagi-org/ai-goofish-monitor) | 17,166 | 2,908 | Python | 基于 Playwright 和AI实现的闲鱼多任务实时/定时监控与智能分析系统，配备了功能完善的后台管理UI。帮助用户从闲鱼海量商品中，找到心仪产品。 |
| 10 | [vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop) | 15,272 | 1,063 | Rust | Computer use CLI for AI agents |
