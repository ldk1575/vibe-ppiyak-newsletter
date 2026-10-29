"""
graph.py - 나만의 뉴스레터 에이전트 LangGraph 메인 워크플로우
브랜드: 🐣 바이브삐약 오픈소스 모닝 브리핑 (봇 이름: 🐣 코딩삐약이)
주제: 깃허브 트렌드 인기 오픈소스 (타깃: AI 에이전트·바이브코딩 입문자)
필수 5단계:
  1. 자료 수집 (collect_rss) - 금지된 6개 RSS 차단 + 채택 3개 채널 수집 + 소스별 실패 격리
  2. 자료 선별 (filter_prelim -> filter_final) - 예선(규칙 + 배치 LLM) / 본선(배치 가중치 채점 Top 3~5)
  3. 요약 및 인사이트 추출 (fetch_and_summarize) - 본문(README) 크롤링 + 3줄 요약 + 입문자용 실전 인사이트
  4. 자동 검수 및 예외 처리 (evaluate_summary -> route_after_eval -> regenerate_summary)
     - 규칙 검수(원문에 없는 숫자) → LLM 검수(audience.yaml checks) → 재생성 최대 N회 → 그래도 실패면 skip
  5. 최종 발행 (publish_newsletter) - 로컬 Markdown/HTML + Discord 웹훅 + store/metrics.jsonl 기록

초안(제미나이 Argon) 대비 바뀐 점은 TECH_SPEC.md '초안 대비 변경' 표에 정리했다.
"""

from __future__ import annotations

import calendar
import datetime
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, TypedDict
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
KST = datetime.timezone(datetime.timedelta(hours=9))  # Actions 러너는 UTC라 날짜를 KST로 고정
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VibePpiyakNewsletterBot/1.0)"}


# ==============================================================================
# 1. 상태(State) 및 구조화 출력(Structured Output) 스키마 정의
# ==============================================================================

class ArticleItem(TypedDict):
    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    published_at: str
    raw_summary: str
    full_text: str
    rss_text: str                 # RSS 가 준 본문 전체 (raw_summary 는 선별용으로 800자 자른 것)
    body_source: str              # readme | page | rss_only | rss_fallback
    # 2단계 선별 로그
    prelim_passed: bool
    prelim_reason: str
    score: float
    score_breakdown: Dict[str, float]
    score_reason: str
    # 3단계 요약 및 인사이트
    summary: str
    beginner_insight: str
    difficulty_stars: str
    # 4단계 자동 검수 및 재시도
    eval_status: Literal["pending", "pass", "retry", "skip"]
    eval_feedback: str
    retry_count: int


class NewsletterState(TypedDict):
    run_id: str
    audience_config: Dict[str, Any]
    raw_articles: List[ArticleItem]
    prelim_articles: List[ArticleItem]
    selected_articles: List[ArticleItem]
    final_articles: List[ArticleItem]
    trending_repos: List[Dict[str, str]]  # 오늘 GitHub 트렌딩 저장소 (순위 후보)
    github_ranking: List[Dict[str, Any]]  # 스타 순 1~10위
    metrics: Dict[str, Any]
    published_files: Dict[str, str]
    webhook_sent: Dict[str, Any]


# LLM 구조화 출력용 Pydantic 모델
class PrelimBatchDecision(BaseModel):
    id: str = Field(description="기사 고유 ID (입력의 id를 그대로)")
    passed: bool = Field(description="예선 통과 여부 (AI 에이전트/바이브코딩/오픈소스 관련성)")
    reason: str = Field(description="통과 또는 탈락 판단 근거 (1문장, 한국어)")


class PrelimBatchOutput(BaseModel):
    decisions: List[PrelimBatchDecision]


class FinalScoreItem(BaseModel):
    id: str = Field(description="기사 고유 ID (입력의 id를 그대로)")
    beginner_accessibility: float = Field(description="입문자 접근성 점수 (0.0~1.0)")
    vibe_coding_utility: float = Field(description="바이브코딩/에이전트 실용성 점수 (0.0~1.0)")
    trend_momentum: float = Field(description="트렌드 화제성 점수 (0.0~1.0)")
    score_reason: str = Field(description="채점 근거 요약 (1문장, 한국어)")


class FinalScoreBatch(BaseModel):
    scores: List[FinalScoreItem]


class SummaryInsightOutput(BaseModel):
    summary: str = Field(description="핵심 내용 및 주요 기능 3줄 요약 (각 줄은 '- '로 시작, 한국어)")
    beginner_insight: str = Field(
        description="AI 에이전트·바이브코딩 입문자(병아리 빌더)가 오늘 바로 활용할 수 있는 실전 팁과 적용 시나리오 (2~3문장, 한국어)"
    )
    difficulty_stars: str = Field(description="입문자 설치·도입 난이도: '🐣 쉬움 ★☆☆' / '🐥 보통 ★★☆' / '🐓 도전 ★★★' 중 하나")


class EvaluationOutput(BaseModel):
    passed: bool = Field(description="검수 통과 여부 (모든 기준 충족 시 true)")
    feedback: str = Field(description="불통과 시 구체적인 수정 지시사항, 통과 시 검증 완료 사유 (한국어)")


# ==============================================================================
# 2. 공용 도구 — LLM · 키워드 규칙 · 숫자 대조 · 기록
# ==============================================================================

LLM_STATS: Dict[str, Any] = {"calls": 0, "errors": 0, "by_stage": {}}
_RATE_LIMITER: InMemoryRateLimiter | None = None


def get_llm(temperature: float = 0.1, thinking_level: str | None = None):
    """Gemini 채팅 모델. 무료 한도(분당 호출 수)를 넘지 않게 레이트 리미터를 공유한다.
    thinking_level 기본값 low — 기본(생각 길게)은 짧은 답에도 생각 토큰 470개·6초를 써서, 분류·채점에는 low 로 충분했다.
    검수만 medium 으로 올린다 (원문 대조는 꼼꼼해야 해서)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    global _RATE_LIMITER
    if _RATE_LIMITER is None:
        rps = float(os.getenv("LLM_REQUESTS_PER_SECOND", "0.15"))  # 0.15 = 분당 9회
        _RATE_LIMITER = InMemoryRateLimiter(requests_per_second=rps, check_every_n_seconds=0.2, max_bucket_size=1)
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        google_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        temperature=temperature,
        thinking_level=thinking_level or os.getenv("GEMINI_THINKING_LEVEL", "low"),
        max_retries=6,
        timeout=120,
        rate_limiter=_RATE_LIMITER,
    )


def call_llm(stage: str, chain, inputs: Dict[str, Any]):
    """모든 LLM 호출이 지나는 한 곳. 단계별 호출 수·오류 수를 metrics에 남긴다. 실패는 호출자에게 예외로 넘긴다."""
    LLM_STATS["calls"] += 1
    LLM_STATS["by_stage"][stage] = LLM_STATS["by_stage"].get(stage, 0) + 1
    try:
        result = chain.invoke(inputs)
        if result is None:
            raise ValueError("구조화 출력이 비어 있음")
        return result
    except Exception:
        LLM_STATS["errors"] += 1
        raise


def keyword_hit(text: str, keywords: List[str]) -> str | None:
    """걸린 키워드를 돌려준다. 영문은 단어 경계로(crypto ≠ cryptography), 한글은 부분 일치로."""
    low = text.lower()
    for kw in keywords:
        k = kw.lower()
        if re.fullmatch(r"[a-z0-9.\- ]+", k):
            if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", low):
                return kw
        elif k in low:
            return kw
    return None


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_not_in_source(generated: str, source: str) -> List[str]:
    """생성문에 있는 두 자리 이상 숫자 중 원문에 없는 것. 한 자리 숫자는 목록 번호 오탐이 많아 뺀다."""
    src = source.replace(",", "")
    src_nums = set(_NUM_RE.findall(src))
    missing = []
    for raw in _NUM_RE.findall(generated):
        n = raw.replace(",", "").rstrip(".")
        if len(n.replace(".", "")) < 2:
            continue
        if n not in src_nums and n not in src:
            missing.append(raw)
    return sorted(set(missing))


def normalize_url(url: str) -> str:
    u = url.strip()
    return u[:-1] if u.endswith("/") else u


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def load_history(store_dir: Path) -> Dict[str, str]:
    path = store_dir / "published_history.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _log_select(metrics: Dict[str, Any], **row: Any) -> None:
    metrics["selection_logs"].append(row)


def _timed(metrics: Dict[str, Any], node: str, t0: float) -> None:
    metrics["node_seconds"][node] = round(time.perf_counter() - t0, 2)


# ==============================================================================
# 3. 노드(Node) 구현
# ==============================================================================

def load_config_node(state: NewsletterState) -> Dict[str, Any]:
    """[초기화] audience.yaml 설정 파일을 로드하고 실행 메트릭 구조를 초기화합니다."""
    config_path = Path(os.getenv("AUDIENCE_CONFIG", ROOT / "audience.yaml"))
    audience_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    now = datetime.datetime.now(KST)
    run_id = now.strftime("%Y%m%d_%H%M%S")
    LLM_STATS.update({"calls": 0, "errors": 0, "by_stage": {}})
    metrics = {
        "run_id": run_id,
        "timestamp": now.isoformat(),
        "trigger": os.getenv("RUN_TRIGGER", "local"),
        "model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        "dry_run": os.getenv("DRY_RUN", "0") == "1",
        "source_counts": {},
        "source_errors": {},
        "funnel": {
            "collected_total": 0,
            "prelim_rule_dropped": 0,
            "prelim_passed": 0,
            "final_scored": 0,
            "final_selected": 0,
            "eval_passed": 0,
            "eval_retried": 0,
            "eval_skipped": 0,
            "published": 0,
        },
        "node_seconds": {},
        "selection_logs": [],
        "evaluation_logs": [],
    }
    return {
        "run_id": run_id,
        "audience_config": audience_config,
        "raw_articles": [],
        "prelim_articles": [],
        "selected_articles": [],
        "final_articles": [],
        "trending_repos": [],
        "github_ranking": [],
        "metrics": metrics,
        "published_files": {},
        "webhook_sent": {"discord": False},
    }


def _fetch_feed(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if not feed.entries:
        raise ValueError("항목 0건")
    return feed


def collect_rss_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [1단계: 자료 수집]
    - 금지된 6개 소스(URL·도메인)를 하드 차단하고 채택된 소스에서 RSS 데이터를 수집합니다.
    - 소스 하나가 실패해도 backup_url → 건너뛰기 순으로 처리하고 나머지 소스로 계속합니다.
    - URL 기준으로 중복 기사를 제거하고, max_age_hours 보다 오래된 글은 뺍니다.
    """
    t0 = time.perf_counter()
    config = state["audience_config"]
    src_cfg = config["sources"]
    excluded_urls = {normalize_url(u) for u in src_cfg["excluded_urls"]}
    excluded_domains = {d.lower() for d in src_cfg.get("excluded_domains", [])}
    per_source = int(src_cfg.get("max_items_per_source", 25))
    max_age_h = float(src_cfg.get("max_age_hours", 72))
    now = datetime.datetime.now(datetime.timezone.utc)

    # 금지 소스 검증 게이트 — 수집을 시작하기 전에 설정 전체를 검사한다
    for src in src_cfg["adopted"]:
        for key in ("url", "backup_url"):
            u = src.get(key)
            if not u:
                continue
            dom = _domain(u)
            if normalize_url(u) in excluded_urls or any(dom == d or dom.endswith("." + d) for d in excluded_domains):
                raise ValueError(f"금지된 RSS 소스가 설정에 포함되어 있습니다: {u}")
    if len(src_cfg["adopted"]) < 3:
        raise ValueError("과제 요건: 채택 소스는 3곳 이상이어야 합니다.")

    collected: List[ArticleItem] = []
    seen_urls: set[str] = set()
    source_counts: Dict[str, int] = {}
    source_errors: Dict[str, str] = {}
    trending_repos: List[Dict[str, str]] = []

    for src in src_cfg["adopted"]:
        src_id, src_name = src["id"], src["name"]
        feed = None
        errors = []
        for u in (src["url"], src.get("backup_url")):
            if not u:
                continue
            try:
                feed = _fetch_feed(u)
                break
            except Exception as e:
                errors.append(f"{u} → {type(e).__name__}: {e}"[:200])
        if errors:
            source_errors[src_id] = " | ".join(errors) + (" (백업으로 수집)" if feed else " (건너뜀)")
        if feed is None:
            source_counts[src_id] = 0
            continue
        if src_id == config.get("github_ranking", {}).get("source_id"):
            # 순위표 후보 — 선별용 상한·신선도와 상관없이 트렌딩 목록 전체
            trending_repos = _repos_from_feed(feed)

        count = too_old = 0
        for entry in feed.entries:
            if count >= per_source:
                break
            link = normalize_url(getattr(entry, "link", "") or "")
            if not link or link in seen_urls:
                continue
            ts = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if ts:
                published = datetime.datetime.fromtimestamp(calendar.timegm(ts), datetime.timezone.utc)
                if (now - published).total_seconds() / 3600 > max_age_h:
                    too_old += 1
                    continue
                published_at = published.astimezone(KST).isoformat()
            else:
                published_at = ""
            seen_urls.add(link)

            raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            contents = [c.get("value", "") for c in (getattr(entry, "content", None) or [])]
            rss_html = max([raw_summary, *contents], key=len)
            rss_text = re.sub(r"\s+", " ", BeautifulSoup(rss_html, "html.parser").get_text(" ", strip=True))
            clean_summary = rss_text[:800]
            collected.append({
                "id": hashlib.md5(link.encode("utf-8")).hexdigest()[:8],
                "title": (getattr(entry, "title", "") or "제목 없음").strip(),
                "url": link,
                "source_id": src_id,
                "source_name": src_name,
                "published_at": published_at,
                "raw_summary": clean_summary,
                "rss_text": rss_text,
                "full_text": "",
                "body_source": "",
                "prelim_passed": False,
                "prelim_reason": "",
                "score": 0.0,
                "score_breakdown": {},
                "score_reason": "",
                "summary": "",
                "beginner_insight": "",
                "difficulty_stars": "",
                "eval_status": "pending",
                "eval_feedback": "",
                "retry_count": 0,
            })
            count += 1
        source_counts[src_id] = count
        if too_old:
            source_counts[f"{src_id}_too_old_dropped"] = too_old

    metrics = state["metrics"]
    metrics["source_counts"] = source_counts
    metrics["source_errors"] = source_errors
    metrics["funnel"]["collected_total"] = len(collected)
    _timed(metrics, "collect_rss", t0)
    return {"raw_articles": collected, "trending_repos": trending_repos, "metrics": metrics}


_REPO_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#?]+)$")


def _repos_from_feed(feed) -> List[Dict[str, str]]:
    repos = []
    for entry in feed.entries:
        m = _REPO_RE.match(normalize_url(getattr(entry, "link", "") or ""))
        if m:
            repos.append({"full_name": f"{m.group(1)}/{m.group(2)}", "url": m.group(0)})
    return repos


def rank_github_stars_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [1단계 부가: 🏆 오늘의 GitHub 트렌딩 스타 순위]
    - 오늘 트렌딩에 오른 저장소의 누적 스타 수를 GitHub REST API(/repos/{owner}/{repo})로 받아 많은 순으로 1~top_n 위를 매깁니다.
    - 후보가 top_n 보다 적으면 extra_feeds(언어별 트렌딩)로 채웁니다.
    - API 가 실패한 저장소는 빼고, 전부 실패하면 순위 섹션 없이 발행합니다 (뉴스레터는 멈추지 않는다).
    """
    t0 = time.perf_counter()
    cfg = state["audience_config"].get("github_ranking", {})
    metrics = state["metrics"]
    if not cfg.get("enabled"):
        return {"github_ranking": []}
    top_n = int(cfg.get("top_n", 10))

    pool: Dict[str, Dict[str, str]] = {r["full_name"].lower(): {**r, "feed": "all"} for r in state.get("trending_repos", [])}
    for feed_url in cfg.get("extra_feeds", []):
        if len(pool) >= top_n:
            break
        try:
            lang = feed_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".xml")
            for r in _repos_from_feed(_fetch_feed(feed_url)):
                pool.setdefault(r["full_name"].lower(), {**r, "feed": lang})
        except Exception as e:
            metrics.setdefault("github_ranking_errors", []).append(f"{feed_url} → {type(e).__name__}")

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", **HEADERS}
    if os.getenv("GITHUB_TOKEN"):  # Actions 에서는 시간당 1000회, 없으면 60회
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    rows, errors = [], []
    for r in pool.values():
        try:
            resp = requests.get(f"https://api.github.com/repos/{r['full_name']}", headers=headers, timeout=10)
            resp.raise_for_status()
            d = resp.json()
            rows.append({
                "full_name": d["full_name"],
                "url": d["html_url"],
                "stars": int(d["stargazers_count"]),
                "forks": int(d["forks_count"]),
                "language": d.get("language") or "-",
                "description": (d.get("description") or "").strip(),
                "trending_feed": r["feed"],
            })
        except Exception as e:
            errors.append(f"{r['full_name']} → {type(e).__name__}")

    # 큐레이션과 같은 제외 키워드를 순위표에도 적용한다 (채용·코인 저장소가 순위에 끼지 않게)
    exclude = state["audience_config"]["selection_criteria"]["preliminary"].get("exclude_keywords", [])
    dropped = [r["full_name"] for r in rows if keyword_hit(f"{r['full_name']} {r['description']}", exclude)]
    rows = [r for r in rows if r["full_name"] not in dropped]
    rows.sort(key=lambda x: x["stars"], reverse=True)
    ranking = [{"rank": i, **row} for i, row in enumerate(rows[:top_n], 1)]
    metrics["github_ranking"] = {
        "fetched_at": datetime.datetime.now(KST).isoformat(),
        "candidates": len(pool),
        "api_ok": len(rows),
        "api_errors": errors,
        "excluded_by_keyword": dropped,
        "top": [{k: x[k] for k in ("rank", "full_name", "stars", "language", "trending_feed")} for x in ranking],
    }
    _timed(metrics, "rank_github_stars", t0)
    return {"github_ranking": ranking, "metrics": metrics}


PRELIM_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 '🐣 바이브삐약 오픈소스 모닝 브리핑'의 예선 심사위원입니다.\n"
        "독자: {persona}\n"
        "판단 기준 문장: {importance_question}\n"
        "주어진 기사 묶음(Batch)의 모든 항목에 대해 하나도 빠짐없이 판정하세요. "
        "오픈소스 프로젝트·AI 에이전트·바이브코딩(Claude Code, Cursor, MCP, CLI 도구 등)과 관련이 있고 "
        "위 판단 기준에 비추어 독자에게 쓸모가 있을 만한 항목만 passed=true로 판정합니다. "
        "id는 입력의 값을 그대로 쓰고, reason은 한국어 1문장으로 씁니다.",
    ),
    ("human", "검토할 기사 묶음 ({n}건):\n{batch_json}"),
])


def run_prelim_batches(articles: List[ArticleItem], batch_size: int, config: Dict[str, Any]) -> Dict[str, Any]:
    """예선 LLM 배치 판정. 노드와 tools/batch_experiment.py 가 같은 함수를 쓴다."""
    llm = get_llm(temperature=0.0).with_structured_output(PrelimBatchOutput)
    chain = PRELIM_PROMPT | llm
    decisions: Dict[str, PrelimBatchDecision] = {}
    stats = {"batch_size": batch_size, "calls": 0, "failed_calls": 0, "seconds": 0.0}
    t0 = time.perf_counter()
    for i in range(0, len(articles), batch_size):
        batch = articles[i: i + batch_size]
        payload = [
            {"id": a["id"], "title": a["title"], "source": a["source_name"], "url": a["url"], "snippet": a["raw_summary"][:250]}
            for a in batch
        ]
        stats["calls"] += 1
        try:
            result: PrelimBatchOutput = call_llm("prelim", chain, {
                "persona": config["audience"]["persona"],
                "importance_question": config["selection_criteria"]["importance_question"].strip(),
                "n": len(batch),
                "batch_json": json.dumps(payload, ensure_ascii=False),
            })
            ids = {a["id"] for a in batch}
            for d in result.decisions:
                if d.id in ids:
                    decisions[d.id] = d
        except Exception:
            stats["failed_calls"] += 1
    stats["seconds"] = round(time.perf_counter() - t0, 2)
    stats["missing"] = sum(1 for a in articles if a["id"] not in decisions)
    stats["missing_rate_pct"] = round(100 * stats["missing"] / len(articles), 1) if articles else 0.0
    return {"decisions": decisions, "stats": stats}


def filter_prelim_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [2단계-A: 예선 선별 (규칙 → Batch LLM 1차 필터링)]
    - 규칙: 제외 키워드, 최근 dedup_days 안에 발행한 URL은 LLM 호출 전에 0원으로 탈락시킵니다.
    - LLM: batch_size 단위로 묶어 관련성을 판정합니다. 판정이 누락된 기사는 include_keywords 로 대체 판정합니다.
    """
    t0 = time.perf_counter()
    config = state["audience_config"]
    pre = config["selection_criteria"]["preliminary"]
    batch_size = int(pre.get("batch_size", 10))
    store_dir = ROOT / config["publishing"].get("store_dir", "store")
    history = load_history(store_dir)
    cutoff = (datetime.datetime.now(KST) - datetime.timedelta(days=int(pre.get("dedup_days", 7)))).date().isoformat()
    recent_urls = {u for u, d in history.items() if d >= cutoff}

    metrics = state["metrics"]
    rule_filtered: List[ArticleItem] = []
    for item in state["raw_articles"]:
        bad = keyword_hit(f"{item['title']} {item['raw_summary']} {item['url']}", pre.get("exclude_keywords", []))
        if bad or item["url"] in recent_urls:
            item["prelim_passed"] = False
            item["prelim_reason"] = (
                f"제외 키워드 '{bad}' 포함으로 규칙 탈락" if bad else f"최근 발행 이력({history[item['url']]})으로 중복 탈락"
            )
            _log_select(metrics, stage="prelim_rule", id=item["id"], title=item["title"], source=item["source_id"],
                        passed=False, reason=item["prelim_reason"])
            continue
        rule_filtered.append(item)
    metrics["funnel"]["prelim_rule_dropped"] = len(state["raw_articles"]) - len(rule_filtered)

    batch = run_prelim_batches(rule_filtered, batch_size, config)
    metrics["prelim_batch_stats"] = batch["stats"]
    include_kws = pre.get("include_keywords", [])

    passed_list: List[ArticleItem] = []
    for a in rule_filtered:
        dec = batch["decisions"].get(a["id"])
        if dec:
            a["prelim_passed"], a["prelim_reason"], decided_by = dec.passed, dec.reason, "llm"
        else:
            hit = keyword_hit(f"{a['title']} {a['raw_summary']} {a['url']}", include_kws)
            a["prelim_passed"] = bool(hit)
            a["prelim_reason"] = f"LLM 판정 누락 → 키워드 '{hit}' 매칭 통과" if hit else "LLM 판정 누락 → 관련 키워드 미포함"
            decided_by = "keyword_fallback"
        _log_select(metrics, stage="prelim_batch", id=a["id"], title=a["title"], source=a["source_id"],
                    passed=a["prelim_passed"], decided_by=decided_by, reason=a["prelim_reason"])
        if a["prelim_passed"]:
            passed_list.append(a)

    metrics["funnel"]["prelim_passed"] = len(passed_list)
    _timed(metrics, "filter_prelim", t0)
    return {"prelim_articles": passed_list, "metrics": metrics}


FINAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{rubric_prompt}\n판단 기준 문장: {importance_question}\n입력된 모든 항목을 하나도 빠짐없이 채점하고 id는 입력값을 그대로 쓰세요."),
    ("human", "채점할 후보 ({n}건):\n{batch_json}"),
])


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def filter_final_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [2단계-B: 본선 선별 (중요도 가중치 채점 및 Top 3~5 선정)]
    - 3축 점수를 묶음 단위로 받아 audience.yaml 가중치(40/40/20)로 가중합합니다.
    - min_score 이상을 점수순으로 top_k 까지, 한 소스 max_per_source 건 이하로 고릅니다.
    - min_score 통과가 min_k 보다 적으면 차점자로 채우고 선발 사유에 '하한 채우기'로 남깁니다.
    """
    t0 = time.perf_counter()
    cfg = state["audience_config"]["selection_criteria"]
    sc = cfg["final_scoring"]
    weights = sc["weights"]
    top_k, min_k = int(sc.get("top_k", 4)), int(sc.get("min_k", 3))
    min_score, max_per_source = float(sc.get("min_score", 0.7)), int(sc.get("max_per_source", 2))
    batch_size = int(sc.get("batch_size", 10))

    chain = FINAL_PROMPT | get_llm(temperature=0.1).with_structured_output(FinalScoreBatch)
    candidates = state["prelim_articles"]
    scores: Dict[str, FinalScoreItem] = {}

    def score_batches(items: List[ArticleItem]) -> None:
        for i in range(0, len(items), batch_size):
            batch = items[i: i + batch_size]
            payload = [
                {"id": a["id"], "title": a["title"], "source": a["source_name"], "url": a["url"], "summary": a["raw_summary"][:500]}
                for a in batch
            ]
            try:
                res: FinalScoreBatch = call_llm("final", chain, {
                    "rubric_prompt": sc["rubric_prompt"].strip(),
                    "importance_question": cfg["importance_question"].strip(),
                    "n": len(batch),
                    "batch_json": json.dumps(payload, ensure_ascii=False),
                })
                ids = {a["id"] for a in batch}
                for s in res.scores:
                    if s.id in ids:
                        scores[s.id] = s
            except Exception:
                pass

    score_batches(candidates)
    missing = [a for a in candidates if a["id"] not in scores]
    if missing:  # 누락분만 한 번 더
        score_batches(missing)

    metrics = state["metrics"]
    for item in candidates:
        s = scores.get(item["id"])
        if s:
            bd = {k: _clamp(getattr(s, k)) for k in ("beginner_accessibility", "vibe_coding_utility", "trend_momentum")}
            item["score_breakdown"] = bd
            item["score"] = round(sum(bd[k] * weights[k] for k in bd), 3)
            item["score_reason"] = s.score_reason
        else:
            item["score"], item["score_breakdown"], item["score_reason"] = 0.0, {}, "채점 실패(LLM 응답 누락) — 0점 처리"

    ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
    selected: List[ArticleItem] = []
    per_src: Dict[str, int] = {}
    why: Dict[str, str] = {}

    def take(item: ArticleItem, reason: str) -> None:
        selected.append(item)
        per_src[item["source_id"]] = per_src.get(item["source_id"], 0) + 1
        why[item["id"]] = reason

    for item in ranked:  # 1차: 기준 통과자
        if len(selected) >= top_k:
            break
        if item["score"] >= min_score and per_src.get(item["source_id"], 0) < max_per_source:
            take(item, f"min_score {min_score} 이상")
    for item in ranked:  # 2차: 하한 채우기
        if len(selected) >= min_k:
            break
        if item["id"] not in why and item["score"] > 0 and per_src.get(item["source_id"], 0) < max_per_source:
            take(item, f"하한 {min_k}건 채우기 (min_score 미달)")

    for rank, item in enumerate(ranked, 1):
        _log_select(metrics, stage="final_scoring", id=item["id"], title=item["title"], source=item["source_id"],
                    rank=rank, score=item["score"], breakdown=item["score_breakdown"], reason=item["score_reason"],
                    selected=item["id"] in why, selected_reason=why.get(item["id"], ""))

    metrics["funnel"]["final_scored"] = len(scores)
    metrics["funnel"]["final_selected"] = len(selected)
    _timed(metrics, "filter_final", t0)
    return {"selected_articles": selected, "metrics": metrics}


def _fetch_article_body(url: str, fallback_summary: str, max_chars: int, min_chars: int,
                        no_fetch_domains: List[str] | None = None) -> tuple[str, str]:
    """선별된 기사의 실제 웹페이지/GitHub README 본문을 크롤링합니다. (본문, 출처 라벨)
    봇을 막는 도메인은 요청하지 않고 RSS 본문(rss_only)을 쓴다. 크롤링이 실패하면 RSS 본문(rss_fallback)."""
    dom = _domain(url)
    if any(dom == d or dom.endswith("." + d) for d in (no_fetch_domains or [])):
        return fallback_summary[:max_chars], "rss_only"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
        readme_el = soup.select_one("article.markdown-body")
        label = "readme"
        if readme_el is None:
            readme_el = soup.select_one("#topic_contents") or soup.select_one("article") or soup.select_one("main") or soup.body
            label = "page"
        text = readme_el.get_text(" ", strip=True) if readme_el else soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= min_chars:
            return text[:max_chars], label
    except Exception:
        pass
    return fallback_summary[:max_chars], "rss_fallback"


SUMMARY_SYSTEM = (
    "당신은 '{persona}'를 위한 오픈소스 큐레이터 '🐣 코딩삐약이'입니다. 말투: {tone}\n"
    "반드시 제공된 원문 본문에 있는 사실만 바탕으로 한국어로 작성하고, 원문에 없는 수치·기능·명령어를 절대 지어내지 마세요. "
    "숫자(스타 수, 버전, 속도 등)는 원문에 적힌 그대로만 쓰고, 원문에 없으면 숫자를 쓰지 마세요. 프로젝트 이름은 원문 표기를 그대로 씁니다.\n"
    "1) summary: 이 오픈소스/소식이 무엇이고 어떤 문제를 해결하는지 3줄로 요약하세요. 각 줄은 '- '로 시작합니다.\n"
    "2) beginner_insight: AI 에이전트 입문자나 바이브코딩 입문자가 내 프로젝트나 실습에 어떻게 바로 써볼 수 있는지 구체적인 활용 팁을 2~3문장으로 제시하세요.\n"
    "3) difficulty_stars: 설치 및 입문 난이도를 '🐣 쉬움 ★☆☆', '🐥 보통 ★★☆', '🐓 도전 ★★★' 중 하나로 표시하세요.\n"
    "원문이 짧은 미리보기뿐이면(본문 출처가 rss_only/rss_fallback) 3줄을 채우려고 내용을 늘리지 말고, 원문에 있는 사실만으로 2~3줄을 쓰고 "
    "인사이트도 원문에서 확인되는 범위의 활용법만 제시하세요."
)

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SUMMARY_SYSTEM),
    ("human", "제목: {title}\nURL: {url}\n선별 이유: {score_reason}\n본문 출처: {body_source} ({body_chars}자)\n원문 본문:\n{full_text}"),
])


def _apply_summary(item: ArticleItem, res: SummaryInsightOutput) -> None:
    item["summary"] = res.summary.strip()
    item["beginner_insight"] = res.beginner_insight.strip()
    item["difficulty_stars"] = res.difficulty_stars.strip()


def fetch_and_summarize_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [3단계: 요약 및 인사이트 추출]
    - 선별된 Top 3~5건의 본문(README/아티클)을 크롤링한 뒤,
      (1) 3줄 핵심 요약과 (2) AI 에이전트·바이브코딩 입문자 맞춤 인사이트를 생성합니다.
    - 요약 호출이 실패한 기사는 skip 으로 표시하고 나머지를 계속 처리합니다.
    """
    t0 = time.perf_counter()
    config = state["audience_config"]
    sm = config.get("summarize", {})
    chain = SUMMARY_PROMPT | get_llm(temperature=0.2).with_structured_output(SummaryInsightOutput)
    metrics = state["metrics"]

    for item in state["selected_articles"]:
        if not item["full_text"]:
            item["full_text"], item["body_source"] = _fetch_article_body(
                item["url"], item.get("rss_text") or item["raw_summary"], int(sm.get("max_body_chars", 6000)),
                int(sm.get("min_body_chars", 300)), sm.get("no_fetch_domains", []),
            )
        try:
            res = call_llm("summarize", chain, {
                "persona": config["audience"]["persona"],
                "tone": config["audience"]["desired_tone"],
                "title": item["title"],
                "url": item["url"],
                "score_reason": item["score_reason"],
                "body_source": item["body_source"],
                "body_chars": len(item["full_text"]),
                "full_text": item["full_text"],
            })
            _apply_summary(item, res)
            item["eval_status"] = "pending"
        except Exception as e:
            item["eval_status"] = "skip"
            item["eval_feedback"] = f"요약 생성 실패로 발행 제외: {type(e).__name__}"
            metrics["funnel"]["eval_skipped"] += 1
            metrics["evaluation_logs"].append({"id": item["id"], "title": item["title"], "retry_count": 0,
                                               "check": "summarize", "eval_status": "skip", "feedback": item["eval_feedback"]})

    metrics["body_sources"] = {a["id"]: {"source": a["body_source"], "chars": len(a["full_text"])} for a in state["selected_articles"]}
    _timed(metrics, "fetch_and_summarize", t0)
    return {"selected_articles": state["selected_articles"], "metrics": metrics}


EVAL_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 뉴스레터 품질 및 팩트체크 검수관(Evaluator)입니다.\n"
        "아래 [원문 본문]과 AI가 작성한 [3줄 요약] 및 [입문자 인사이트]를 대조하여 엄격히 검수하세요.\n"
        "검수 기준:\n{checks}\n"
        "요약(사실 칸)은 원문과 문장 단위로 대조합니다. 인사이트(해석 칸)는 원문에 같은 문장이 없어도 되지만, "
        "원문에 없는 기능·숫자·명령어를 새로 만들면 위반입니다.\n"
        "모든 기준을 충족하면 passed=true, 하나라도 위반하면 passed=false 와 '무엇을 어떻게 고치라'는 구체적인 피드백을 한국어로 반환하세요.",
    ),
    (
        "human",
        "제목: {title}\nURL: {url}\n본문 출처: {body_source} ({body_chars}자 — rss_only/rss_fallback 이면 짧은 미리보기라 요약이 3줄보다 짧아도 정상)\n"
        "[원문 본문]:\n{full_text}\n\n[3줄 요약]:\n{summary}\n\n[입문자 인사이트]:\n{beginner_insight}\n\n[입문 난이도 표기]: {difficulty_stars}",
    ),
])


def evaluate_summary_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [4단계: 자동 검수]
    - 1차 규칙 검수(0원): 요약·인사이트의 두 자리 이상 숫자가 원문에 있는지 대조합니다.
    - 2차 LLM 검수: audience.yaml evaluation_and_retry.checks 를 기준으로 원문과 대조합니다.
    - 불통과 시 retry_count < max_retries 면 retry, 아니면 skip(발행 제외)으로 표시합니다.
    """
    t0 = time.perf_counter()
    er = state["audience_config"]["evaluation_and_retry"]
    max_retries = int(er.get("max_retries", 2))
    checks = "\n".join(f"{i}. {c}" for i, c in enumerate(er.get("checks", []), 1))
    chain = EVAL_PROMPT | get_llm(temperature=0.0, thinking_level=os.getenv("EVAL_THINKING_LEVEL", "medium")).with_structured_output(EvaluationOutput)
    metrics = state["metrics"]

    for item in state["selected_articles"]:
        if item["eval_status"] in ("pass", "skip"):
            continue

        source_text = f"{item['title']} {item['url']} {item['full_text']}"
        bad_numbers = numbers_not_in_source(f"{item['summary']} {item['beginner_insight']}", source_text)
        if bad_numbers:
            passed, check = False, "rule_numbers"
            feedback = f"원문에 없는 숫자 {', '.join(bad_numbers)} 가 들어 있습니다. 원문에 있는 숫자만 쓰거나 숫자를 빼고 다시 쓰세요."
        else:
            check = "llm"
            try:
                res: EvaluationOutput = call_llm("evaluate", chain, {
                    "checks": checks,
                    "title": item["title"],
                    "url": item["url"],
                    "full_text": item["full_text"],
                    "summary": item["summary"],
                    "beginner_insight": item["beginner_insight"],
                    "difficulty_stars": item["difficulty_stars"],
                    "body_source": item["body_source"],
                    "body_chars": len(item["full_text"]),
                })
                passed, feedback = res.passed, res.feedback
            except Exception as e:
                passed, feedback, check = False, f"검수 호출 실패({type(e).__name__}) — 안전을 위해 불통과 처리", "llm_error"

        if passed:
            item["eval_status"] = "pass"
            metrics["funnel"]["eval_passed"] += 1
        elif item["retry_count"] < max_retries:
            item["eval_status"] = "retry"
            metrics["funnel"]["eval_retried"] += 1
        else:
            item["eval_status"] = "skip"
            feedback = f"최대 재시도({max_retries}회) 초과로 발행 제외: {feedback}"
            metrics["funnel"]["eval_skipped"] += 1
        item["eval_feedback"] = feedback

        metrics["evaluation_logs"].append({
            "id": item["id"],
            "title": item["title"],
            "retry_count": item["retry_count"],
            "check": check,
            "eval_status": item["eval_status"],
            "feedback": feedback,
        })

    metrics["node_seconds"]["evaluate_summary"] = round(
        metrics["node_seconds"].get("evaluate_summary", 0) + time.perf_counter() - t0, 2)
    return {"selected_articles": state["selected_articles"], "metrics": metrics}


REGEN_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        SUMMARY_SYSTEM + "\n\n이전 요약본이 검수에서 반려되었습니다. [검수관 지적사항]을 반드시 반영하고, 원문에 없는 내용은 삭제한 뒤 다시 작성하세요.",
    ),
    (
        "human",
        "제목: {title}\nURL: {url}\n본문 출처: {body_source} ({body_chars}자)\n[검수관 지적사항]: {eval_feedback}\n"
        "[이전 요약]: {old_summary}\n[이전 인사이트]: {old_insight}\n[원문 본문]:\n{full_text}",
    ),
])


def regenerate_summary_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [4단계 예외 처리: 재생성(Regenerate)]
    - eval_status == 'retry' 인 기사만 골라 검수관의 피드백(eval_feedback)을 반영해 재작성합니다.
    - 재생성 호출이 실패해도 retry_count 는 올라가므로 루프는 반드시 끝납니다.
    """
    t0 = time.perf_counter()
    config = state["audience_config"]
    chain = REGEN_PROMPT | get_llm(temperature=0.1).with_structured_output(SummaryInsightOutput)

    for item in state["selected_articles"]:
        if item["eval_status"] != "retry":
            continue
        item["retry_count"] += 1
        try:
            res = call_llm("regenerate", chain, {
                "persona": config["audience"]["persona"],
                "tone": config["audience"]["desired_tone"],
                "title": item["title"],
                "url": item["url"],
                "eval_feedback": item["eval_feedback"],
                "old_summary": item["summary"],
                "old_insight": item["beginner_insight"],
                "body_source": item["body_source"],
                "body_chars": len(item["full_text"]),
                "full_text": item["full_text"],
            })
            _apply_summary(item, res)
        except Exception:
            pass  # 이전 요약 그대로 다시 검수 → 횟수 초과 시 skip
        item["eval_status"] = "pending"

    metrics = state["metrics"]
    metrics["node_seconds"]["regenerate_summary"] = round(
        metrics["node_seconds"].get("regenerate_summary", 0) + time.perf_counter() - t0, 2)
    return {"selected_articles": state["selected_articles"], "metrics": metrics}


def route_after_eval(state: NewsletterState) -> Literal["regenerate", "publish"]:
    """검수 결과 'retry' 상태인 기사가 하나라도 있으면 regenerate 노드로 분기하고, 없으면 publish로 이동합니다."""
    needs_retry = any(item["eval_status"] == "retry" for item in state["selected_articles"])
    return "regenerate" if needs_retry else "publish"


# ---- 5단계 발행 도우미 --------------------------------------------------------

# 본문을 못 읽고 RSS 미리보기만으로 요약한 기사는 독자에게 그렇다고 알린다
PREVIEW_NOTE_MD = " · 📎 원문 미리보기 기반 요약 — 자세한 내용은 링크에서"
PREVIEW_NOTE_DISCORD = "\n📎 원문 미리보기 기반 요약 — 자세한 내용은 링크에서"
PREVIEW_BADGE_HTML = '<span class="badge preview">📎 미리보기 기반 요약</span>'


def is_preview(art: ArticleItem) -> bool:
    return art.get("body_source", "").startswith("rss")


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


RANKING_TITLE = "🏆 오늘의 GitHub 트렌딩 TOP {n} (⭐ 누적 스타 순)"
RANKING_NOTE = "오늘 GitHub Trending 에 오른 저장소를 GitHub API 의 누적 스타 수로 줄 세웠어요. 숫자는 {at} 기준."


def _ranking_line_discord(r: Dict[str, Any]) -> str:
    desc = f"\n　{_cut(r['description'], 70)}" if r["description"] else ""
    return f"**{r['rank']}.** [{r['full_name']}]({r['url']}) ⭐ {r['stars']:,} · {r['language']}{desc}"


def _ranking_embed(ranking: List[Dict[str, Any]], fetched_at: str) -> Dict[str, Any] | None:
    if not ranking:
        return None
    body = "\n".join(_ranking_line_discord(r) for r in ranking)
    return {
        "title": RANKING_TITLE.format(n=len(ranking)),
        "description": _cut(RANKING_NOTE.format(at=fetched_at) + "\n\n" + body, 4096),
        "color": 2303786,  # GitHub 다크 (#23272A 근처)
    }


def build_discord_payload(config: Dict[str, Any], final_articles: List[ArticleItem], funnel: Dict[str, int], today: str,
                          ranking: List[Dict[str, Any]] | None = None, ranking_at: str = "") -> Dict[str, Any]:
    """디스코드 한도(본문 2000자, embed 10개, 제목 256자, 필드 1024자, 합계 6000자) 안에서 만든다.
    순위표 embed 는 맨 뒤에 붙이고, 그 크기만큼 큐레이션 embed 예산에서 먼저 뺀다."""
    nl = config["newsletter"]
    rank_embed = _ranking_embed(ranking or [], ranking_at)
    rank_size = len(rank_embed["title"]) + len(rank_embed["description"]) if rank_embed else 0
    if not final_articles:
        return {
            "username": nl.get("bot_name", "🐣 코딩삐약이"),
            "content": f"🐣 삐약… {nl['name']} ({today})\n오늘은 검수를 통과한 소식이 없어서 쉬어 갈게요. "
                       f"(수집 {funnel['collected_total']}건 → 예선 {funnel['prelim_passed']}건 → 본선 {funnel['final_selected']}건 → 발행 0건)",
            "embeds": [rank_embed] if rank_embed else [],
        }
    embeds, total = [], rank_size
    for idx, art in enumerate(final_articles[:9], 1):
        e = {
            "title": _cut(f"{idx}. {art['title']}", 256),
            "url": art["url"],
            "color": 16098851,  # 병아리 옐로우 (#F5A623)
            "fields": [
                {"name": "📊 선별 지표",
                 "value": _cut(f"출처: **{art['source_name']}** | 중요도: `{art['score']}` | 난이도: {art['difficulty_stars']}"
                               + (PREVIEW_NOTE_DISCORD if is_preview(art) else ""), 1024),
                 "inline": False},
                {"name": "📌 3줄 핵심 요약", "value": _cut(art["summary"], 1024), "inline": False},
                {"name": "🐣 코딩삐약이의 입문자 실전 팁", "value": _cut(art["beginner_insight"], 1024), "inline": False},
            ],
        }
        size = len(e["title"]) + sum(len(f["name"]) + len(f["value"]) for f in e["fields"])
        if total + size > 5800:
            break
        embeds.append(e)
        total += size
    content = (
        f"🐣 **삐약! {nl['name']} ({today}) 배달 왔어요!**\n"
        f"오늘 아침 수집된 {funnel['collected_total']}건 중 예선 {funnel['prelim_passed']}건 → 본선 {funnel['final_selected']}건 → "
        f"팩트체크 검수를 통과한 **{len(embeds)}건**의 알짜 오픈소스입니다 💌"
        + (f"\n맨 아래에 🏆 오늘의 GitHub 트렌딩 스타 순위 TOP {len(ranking)}도 있어요!" if rank_embed else "")
    )
    if rank_embed:
        embeds.append(rank_embed)
    return {"username": nl.get("bot_name", "🐣 코딩삐약이"), "content": _cut(content, 2000), "embeds": embeds}


def send_discord(payload: Dict[str, Any]) -> Dict[str, Any]:
    """웹훅 발송. 주소는 로그·metrics 에 남기지 않는다. DRY_RUN=1 이면 보내지 않는다."""
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if os.getenv("DRY_RUN", "0") == "1":
        return {"discord": False, "status": "dry_run", "embeds": len(payload.get("embeds", []))}
    if not url:
        return {"discord": False, "status": "no_webhook_env"}
    err = "rate_limited"
    for _ in range(3):
        try:
            r = requests.post(url, params={"wait": "true"}, json=payload, timeout=15)
            if r.status_code == 429:  # 디스코드 레이트 리밋 — 안내된 시간만큼 기다렸다 재시도
                time.sleep(float(r.json().get("retry_after", 2)))
                continue
            ok = r.status_code in (200, 204)
            msg_id = r.json().get("id") if ok and r.status_code == 200 else None
            return {"discord": ok, "status": r.status_code, "message_id": msg_id, "embeds": len(payload.get("embeds", []))}
        except Exception as e:
            err = type(e).__name__
    return {"discord": False, "status": f"error: {err}"}


def render_markdown(config: Dict[str, Any], arts: List[ArticleItem], funnel: Dict[str, int], today: str,
                    ranking: List[Dict[str, Any]] | None = None, ranking_at: str = "") -> str:
    nl = config["newsletter"]
    lines = [
        f"# {nl['name']} ({today})",
        "",
        f"> **큐레이터**: {nl.get('bot_name', '🐣 코딩삐약이')} | **타깃 독자**: AI 에이전트 입문자 · 바이브코딩 입문자",
        f"> **오늘의 선별 결과**: 총 {funnel['collected_total']}건 수집 → 예선 {funnel['prelim_passed']}건 통과 → "
        f"본선 {funnel['final_selected']}건 → 최종 {len(arts)}건 검수 완료 💌",
        "",
    ]
    if not arts:
        lines.append("오늘은 검수를 통과한 소식이 없습니다.")
    for idx, art in enumerate(arts, 1):
        lines.extend([
            f"## {idx}. [{art['title']}]({art['url']})",
            f"- **출처**: {art['source_name']} | **중요도 점수**: `{art['score']}` | **입문 난이도**: {art['difficulty_stars']}",
            f"- **선별 이유**: {art['score_reason']}",
            f"- **검수**: 통과 (재생성 {art['retry_count']}회)" + (PREVIEW_NOTE_MD if is_preview(art) else ""),
            "",
            "### 📌 3줄 핵심 요약",
            art["summary"],
            "",
            "### 🐣 코딩삐약이의 입문자 실전 인사이트",
            f"> {art['beginner_insight']}",
            "",
        ])
    if ranking:
        lines.extend([
            "---",
            "",
            f"## {RANKING_TITLE.format(n=len(ranking))}",
            "",
            f"> {RANKING_NOTE.format(at=ranking_at)}",
            "",
            "| 순위 | 저장소 | ⭐ 스타 | 포크 | 언어 | 설명 |",
            "|---:|---|---:|---:|---|---|",
        ])
        for r in ranking:
            desc = _cut(r["description"], 80).replace("|", "\\|")
            lines.append(f"| {r['rank']} | [{r['full_name']}]({r['url']}) | {r['stars']:,} | {r['forks']:,} | {r['language']} | {desc} |")
        lines.append("")
    return "\n".join(lines)


def render_html(config: Dict[str, Any], arts: List[ArticleItem], funnel: Dict[str, int], today: str,
                ranking: List[Dict[str, Any]] | None = None, ranking_at: str = "") -> str:
    """브라우저 캡처용 HTML. 외부에서 온 문자열은 전부 escape 한다."""
    e = html.escape
    nl = config["newsletter"]
    cards = ""
    for idx, art in enumerate(arts, 1):
        cards += f"""
  <div class="card">
    <div class="badge-row">
      <span class="badge source">{e(art['source_name'])}</span>
      <span class="badge score">중요도 {art['score']}</span>
      <span class="badge diff">{e(art['difficulty_stars'])}</span>
      <span class="badge eval">검수 통과 · 재생성 {art['retry_count']}회</span>{PREVIEW_BADGE_HTML if is_preview(art) else ""}
    </div>
    <h2>{idx}. <a href="{e(art['url'])}" target="_blank" rel="noopener">{e(art['title'])}</a></h2>
    <p class="reason"><strong>선별 근거:</strong> {e(art['score_reason'])}</p>
    <div class="summary-box"><h3>📌 3줄 핵심 요약</h3><p>{e(art['summary']).replace(chr(10), '<br>')}</p></div>
    <div class="insight-box"><h3>🐣 코딩삐약이의 입문자 실전 팁</h3><p>{e(art['beginner_insight'])}</p></div>
  </div>"""
    if not arts:
        cards = '<div class="card"><p>오늘은 검수를 통과한 소식이 없습니다.</p></div>'
    if ranking:
        rows = "".join(
            f"""
        <tr><td class="rk">{r['rank']}</td><td><a href="{e(r['url'])}" target="_blank" rel="noopener">{e(r['full_name'])}</a>
          <div class="desc">{e(_cut(r['description'], 90))}</div></td>
          <td class="num">⭐ {r['stars']:,}</td><td class="num">{r['forks']:,}</td><td>{e(r['language'])}</td></tr>"""
            for r in ranking
        )
        cards += f"""
  <div class="card ranking">
    <h2>{e(RANKING_TITLE.format(n=len(ranking)))}</h2>
    <p class="reason">{e(RANKING_NOTE.format(at=ranking_at))}</p>
    <table><thead><tr><th>순위</th><th>저장소</th><th>스타</th><th>포크</th><th>언어</th></tr></thead><tbody>{rows}
    </tbody></table>
  </div>"""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{e(nl['name'])} - {today}</title>
<style>
  body {{ font-family: 'Pretendard', 'Malgun Gothic', -apple-system, sans-serif; background: #fffbeb; color: #1e293b; max-width: 820px; margin: 40px auto; padding: 0 16px; line-height: 1.6; }}
  .header {{ background: linear-gradient(135deg, #fef3c7, #fde68a); border: 2px solid #f59e0b; border-radius: 16px; padding: 28px; margin-bottom: 24px; }}
  .header h1 {{ margin: 0 0 8px 0; font-size: 24px; color: #b45309; }}
  .header p {{ margin: 4px 0; color: #78350f; font-size: 14px; font-weight: 500; }}
  .card {{ background: #ffffff; border: 1px solid #fde68a; border-radius: 14px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(245, 158, 11, 0.08); }}
  .card h2 {{ margin: 10px 0 8px 0; font-size: 19px; }}
  .card h2 a {{ color: #1e293b; text-decoration: none; }}
  .card h2 a:hover {{ color: #d97706; text-decoration: underline; }}
  .badge-row {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .badge {{ font-size: 12px; padding: 4px 10px; border-radius: 999px; font-weight: 600; }}
  .badge.source {{ background: #f1f5f9; color: #475569; }}
  .badge.score {{ background: #fef3c7; color: #b45309; }}
  .badge.diff {{ background: #dcfce7; color: #166534; }}
  .badge.eval {{ background: #e0e7ff; color: #3730a3; }}
  .badge.preview {{ background: #fce7f3; color: #9d174d; }}
  .reason {{ font-size: 13px; color: #64748b; margin-bottom: 14px; }}
  .summary-box {{ background: #f8fafc; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
  .summary-box h3, .insight-box h3 {{ margin: 0 0 6px 0; font-size: 14px; color: #b45309; }}
  .insight-box {{ background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 14px 16px; }}
  .ranking table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .ranking th {{ text-align: left; color: #b45309; font-size: 12px; border-bottom: 2px solid #fde68a; padding: 6px 8px; }}
  .ranking td {{ border-bottom: 1px solid #fef3c7; padding: 8px; vertical-align: top; }}
  .ranking td.rk {{ font-weight: 700; color: #b45309; width: 32px; text-align: center; }}
  .ranking td.num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  .ranking a {{ color: #1e293b; font-weight: 600; text-decoration: none; }}
  .ranking .desc {{ color: #64748b; font-size: 12px; margin-top: 2px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>{e(nl['name'])}</h1>
    <p>발행일: {today} | 큐레이터: {e(nl.get('bot_name', '🐣 코딩삐약이'))} | 타깃: AI 에이전트 · 바이브코딩 입문자</p>
    <p>수집 {funnel['collected_total']}건 → 예선 {funnel['prelim_passed']}건 → 본선 {funnel['final_selected']}건 → 최종 발행 {len(arts)}건 💌</p>
  </div>
  {cards}
</body>
</html>"""


def publish_newsletter_node(state: NewsletterState) -> Dict[str, Any]:
    """
    [5단계: 최종 발행 및 실행 로그 기록]
    1) 검수를 통과('pass')한 기사만 모아 로컬 Markdown 및 HTML 뉴스레터 파일로 저장합니다.
    2) DISCORD_WEBHOOK_URL 이 있으면 '🐣 코딩삐약이' 봇으로 Rich Embed 카드를 전송합니다 (DRY_RUN=1 이면 생략).
    3) 발행한 URL 을 store/published_history.json 에 남겨 다음 실행의 중복 발행을 막습니다.
    4) store/metrics.jsonl 파일에 전체 파이프라인 실행 및 검수 기록을 Append 합니다.
    """
    t0 = time.perf_counter()
    config = state["audience_config"]
    metrics = state["metrics"]
    funnel = metrics["funnel"]
    final_articles = [a for a in state["selected_articles"] if a["eval_status"] == "pass"]
    funnel["published"] = len(final_articles)
    today = datetime.datetime.now(KST).date().isoformat()

    out_dir = ROOT / config["publishing"].get("output_dir", "output")
    store_dir = ROOT / config["publishing"].get("store_dir", "store")
    out_dir.mkdir(parents=True, exist_ok=True)
    store_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"newsletter_{today}.md"
    html_path = out_dir / f"newsletter_{today}.html"
    ranking = state.get("github_ranking", [])
    ranking_at = metrics.get("github_ranking", {}).get("fetched_at", "")[:16].replace("T", " ") + " KST" if ranking else ""
    md_path.write_text(render_markdown(config, final_articles, funnel, today, ranking, ranking_at), encoding="utf-8")
    html_path.write_text(render_html(config, final_articles, funnel, today, ranking, ranking_at), encoding="utf-8")

    webhook_sent = send_discord(build_discord_payload(config, final_articles, funnel, today, ranking, ranking_at))

    # 실제로 발행된 경우에만 이력에 남긴다 (dry-run 은 다음 실행을 막지 않게)
    if webhook_sent.get("discord"):
        history = load_history(store_dir)
        for a in final_articles:
            history[a["url"]] = today
        keep_from = (datetime.datetime.now(KST) - datetime.timedelta(days=30)).date().isoformat()
        history = {u: d for u, d in history.items() if d >= keep_from}
        (store_dir / "published_history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    published_files = {"markdown": md_path.relative_to(ROOT).as_posix(), "html": html_path.relative_to(ROOT).as_posix()}
    metrics["published_files"] = published_files
    metrics["webhook_sent"] = webhook_sent
    metrics["published_articles"] = [
        {"id": a["id"], "title": a["title"], "url": a["url"], "source": a["source_id"], "score": a["score"],
         "retry_count": a["retry_count"], "body_source": a["body_source"]}
        for a in final_articles
    ]
    metrics["llm_stats"] = dict(LLM_STATS)
    _timed(metrics, "publish_newsletter", t0)

    with open(store_dir / "metrics.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

    return {
        "final_articles": final_articles,
        "published_files": published_files,
        "webhook_sent": webhook_sent,
        "metrics": metrics,
    }


# ==============================================================================
# 4. LangGraph 빌더 함수
# ==============================================================================

def build_newsletter_graph():
    """5단계 뉴스레터 에이전트 StateGraph를 조립하고 컴파일합니다."""
    workflow = StateGraph(NewsletterState)

    workflow.add_node("load_config", load_config_node)
    workflow.add_node("collect_rss", collect_rss_node)
    workflow.add_node("rank_github_stars", rank_github_stars_node)
    workflow.add_node("filter_prelim", filter_prelim_node)
    workflow.add_node("filter_final", filter_final_node)
    workflow.add_node("fetch_and_summarize", fetch_and_summarize_node)
    workflow.add_node("evaluate_summary", evaluate_summary_node)
    workflow.add_node("regenerate_summary", regenerate_summary_node)
    workflow.add_node("publish_newsletter", publish_newsletter_node)

    workflow.add_edge(START, "load_config")
    workflow.add_edge("load_config", "collect_rss")
    workflow.add_edge("collect_rss", "rank_github_stars")
    workflow.add_edge("rank_github_stars", "filter_prelim")
    workflow.add_edge("filter_prelim", "filter_final")
    workflow.add_edge("filter_final", "fetch_and_summarize")
    workflow.add_edge("fetch_and_summarize", "evaluate_summary")

    workflow.add_conditional_edges(
        "evaluate_summary",
        route_after_eval,
        {
            "regenerate": "regenerate_summary",
            "publish": "publish_newsletter",
        },
    )
    workflow.add_edge("regenerate_summary", "evaluate_summary")
    workflow.add_edge("publish_newsletter", END)

    return workflow.compile()
