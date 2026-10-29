# 🐣 바이브삐약 오픈소스 모닝 브리핑 (2026-10-29)

> **큐레이터**: 🐣 코딩삐약이 | **타깃 독자**: AI 에이전트 입문자 · 바이브코딩 입문자
> **오늘의 선별 결과**: 총 42건 수집 → 예선 15건 통과 → 본선 4건 → 최종 4건 검수 완료 💌

## 1. [elayadesign/ai-design-skills](https://github.com/elayadesign/ai-design-skills)
- **출처**: GitHub Trending Daily | **중요도 점수**: `0.93` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: Cursor나 Claude Code 규칙 파일에 마크다운만 복사하면 즉시 고품질 랜딩페이지를 뽑아낼 수 있어 입문자 바이브코딩에 최적입니다.
- **검수**: 통과 (재생성 0회)

### 📌 3줄 핵심 요약
- Claude Code, Cursor, Codex, Windsurf 등 마크다운 규칙 파일을 읽는 AI 코딩 도구를 위한 디자인 스킬 모음집입니다.
- 'landing-page-design' 스킬을 통해 요구사항 질문부터 페이지 구조, 전환 카피, 타이포·여백·모션 등 전체 비주얼 시스템을 포함한 랜딩페이지를 처음부터 제작합니다.
- 각 도구별 규칙 경로(.cursor/rules, AGENTS.md, .windsurfrules 등)나 Claude.ai 대화창에 SKILL.md 파일을 넣어 간편하게 적용할 수 있습니다.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> 랜딩페이지를 만들 때 Cursor의 규칙 설정이나 Claude.ai 대화방에 SKILL.md 파일만 복사해 넣으면 AI가 전문적인 디자인 시스템을 갖춰 코딩을 시작해요. 파일 하단에 있는 폰트, 색상, 여백 등 디자인 수치 섹션만 내 취향대로 살짝 수정해주면 나만의 브랜드 스타일에 맞게 즉시 커스텀할 수 있답니다!

## 2. [Nutlope/hallmark](https://github.com/Nutlope/hallmark)
- **출처**: GitHub Trending Daily | **중요도 점수**: `0.92` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: 천편일률적인 AI 특유의 웹 디자인을 탈피하게 돕는 스킬 팩으로, 코딩 에이전트에 쉽게 붙여 실전 프론트엔드 퀄리티를 대폭 높여줍니다.
- **검수**: 통과 (재생성 1회)

### 📌 3줄 핵심 요약
- Claude Code, Codex, Cursor 등에서 AI 특유의 뻔한 웹 디자인 티(헤드라인 위 눈썹 텍스트, 자간 넓은 대문자 라벨 등)를 벗어나도록 돕는 디자인 스킬 팩입니다.
- Fifty 테마 머티리얼 카탈로그 또는 프롬프트 기반 커스텀을 지원하며, 755개의 오픈 라이선스 사진과 실제 제품 스크린샷 캡처 기능을 제공합니다.
- 실제 브라우저 기반으로 접근성·대비·반응형 레이아웃을 검사하는 린트(sloplint)와 서브에이전트 리뷰를 거쳐 완성도 높은 독립형 HTML/CSS를 제작합니다.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> AI 코딩 에이전트로 웹 페이지를 만들 때 디자인이 너무 기계 같아 고민이었다면, Node 18 이상 환경에서 'npx skills add nutlope/hallmark -g' 명령어로 간단히 등록해 사용해 보세요. 기존 프로젝트가 있다면 '/hallmark redesign <경로>' 명령으로 기존 기능과 링크 연결은 유지한 채 세련된 레이아웃으로 탈바꿈시킬 수 있답니다!

## 3. [Show GN: anti-stuck - Claude Code가 멈춘 명령·서브에이전트를 영원히 기다리지 않게 하는 플러그인](https://news.hada.io/topic?id=36210)
- **출처**: GeekNews | **중요도 점수**: `0.87` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: Claude Code 사용 중 빈번히 발생하는 MCP 멈춤 현상을 해결해주는 실용적인 플러그인으로 입문자의 답답함을 바로 해결해줍니다.
- **검수**: 통과 (재생성 0회) · 📎 원문 미리보기 기반 요약 — 자세한 내용은 링크에서

### 📌 3줄 핵심 요약
- Claude Code 사용 중 멈춰버린 명령이나 서브에이전트를 무한정 기다리지 않도록 방지해주는 플러그인입니다.
- Marionette MCP 연결이 10분 넘게 멈추는 등 개발 중 발생하는 불필요한 대기 시간 문제를 해결하고자 제작되었습니다.
- MCP 호출은 Bash 타임아웃 밖이며 stdio MCP 기본 유휴 한도가 30분에 달해 생기는 '멈춤 현상'에 대응합니다.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> Claude Code로 바이브코딩을 진행할 때 MCP 도구가 응답 없이 멈춰 서서 소중한 시간을 낭비하는 것을 막아주는 유용한 도구예요! 원문처럼 MCP 호출이 타임아웃 없이 매달리는 상황이 잦다면, 이 플러그인을 도입해 무한 대기 없이 쾌적하게 에이전트 작업을 이어가 보세요 🐣

## 4. [Show HN: Hob - Open-source, on device alternative to Claude Cowork and ChatGPT](https://github.com/FrigadeHQ/hob)
- **출처**: Hacker News: Show HN (points>=20) | **중요도 점수**: `0.87` | **입문 난이도**: 🐣 쉬움 ★☆☆
- **선별 이유**: 로컬 모델과 MCP를 지원하는 무료 오픈소스 데스크톱 앱으로, 복잡한 인프라 없이 즉시 설치해 개인 파일 기반 코딩 및 에이전트 실습을 시작하기에 매우 적합합니다.
- **검수**: 통과 (재생성 0회)

### 📌 3줄 핵심 요약
- Hob은 내 컴퓨터에서 AI를 더 쉽게 사용할 수 있도록 돕는 무료 오픈소스 데스크톱 앱이에요.
- Mac, Windows, Linux를 지원하며 Claude와 ChatGPT의 대안으로 오프라인에서도 프라이빗하게 작동해요.
- 컴퓨터 사양에 맞는 최적의 프론티어 오픈 가중치 모델을 자동으로 선택해 모든 환경 설정을 대신 처리해 줘요.

### 🐣 코딩삐약이의 입문자 실전 인사이트
> 내 컴퓨터에 Hob을 설치하기만 하면 복잡한 환경 설정 없이도 사양에 맞는 오픈 가중치 모델을 바로 실습해 볼 수 있어요! PDF를 채우거나 문서 작업을 안전하게 로컬 환경에서 처리하는 작업부터 가볍게 시작해 보세요.

---

## 🏆 오늘의 GitHub 트렌딩 TOP 10 (⭐ 누적 스타 순)

> 오늘 GitHub Trending 에 오른 저장소를 GitHub API 의 누적 스타 수로 줄 세웠어요. 숫자는 2026-10-29 15:59 KST 기준.

| 순위 | 저장소 | ⭐ 스타 | 포크 | 언어 | 설명 |
|---:|---|---:|---:|---|---|
| 1 | [obra/superpowers](https://github.com/obra/superpowers) | 307,678 | 27,367 | Shell | An agentic skills framework & software development methodology that works. |
| 2 | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 292,000 | 43,230 | JavaScript | The agent harness performance optimization system. Skills, instincts, memory, s… |
| 3 | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 93,486 | 5,517 | Rust | The design vocabulary for your coding agent. Steer with polish and bolder, revi… |
| 4 | [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) | 48,591 | 6,019 | Python | DeepTutor: Lifelong Personalized Tutoring. https://deeptutor.info/. |
| 5 | [Nutlope/hallmark](https://github.com/Nutlope/hallmark) | 41,081 | 2,133 | CSS | Anti-AI-slop design skill for Claude Code, Cursor, and Codex. |
| 6 | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | 40,025 | 7,584 | TypeScript | 📨 The ultimate agentic social media scheduling tool 🤖 |
| 7 | [elayadesign/ai-design-skills](https://github.com/elayadesign/ai-design-skills) | 11,446 | 825 | - |  |
| 8 | [makecindy/cindy](https://github.com/makecindy/cindy) | 8,309 | 975 | TypeScript | Consider it done. The open-source AI agent that works out of the box · 想到，就能做到。… |
| 9 | [togg53192-cmd/jailbreaks](https://github.com/togg53192-cmd/jailbreaks) | 7,543 | 1,073 | - | LIST OF ALL MY JAILBREAKS |
| 10 | [JetBrains/thinkrail](https://github.com/JetBrains/thinkrail) | 5,393 | 273 | TypeScript | Vibe code with pi in a lightweight, real IDE that customises itself around the … |
