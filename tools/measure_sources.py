"""
tools/measure_sources.py - 후보 RSS 소스를 실제로 재서 '소스 채택표'의 숫자를 만든다.

측정 항목 (LLM 호출 없음, 0원)
  - status / 응답 시간 / 수집 건수
  - 오픈소스 URL 포함률: 링크나 요약에 github.com · gitlab.com 이 들어간 비율
  - 관련률: audience.yaml include_keywords 중 '주제 키워드'(github.com · open-source 처럼 저장소 자체를 뜻하는 것은 뺌)가
            제목·요약에 하나라도 걸린 비율 (노이즈율 = 1 - 관련률). github.com 을 넣으면 GitHub 소스는 무조건 100%가 돼서 뺐다.
  - 첫 요청이 5xx 면 3초 뒤 한 번 더 요청하고, 그 사실을 retried 로 남긴다 (2026-10-29 hnrss 가 일시적으로 502를 냈다)
  - 48·72시간 신선도: 발행 시각이 48/72시간 이내인 비율 (시각이 없는 항목은 분모에서 뺀다, 수집 노드의 max_age_hours=72)
  - 요약 길이 중앙값 (RSS만으로 요약 가능한 정보량의 대리 지표)

실행: python tools/measure_sources.py  → store/source_measurement.json 저장 + 마크다운 표 출력
"""

from __future__ import annotations

import calendar
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from graph import keyword_hit  # noqa: E402  같은 키워드 규칙으로 잰다

CANDIDATES = [
    ("github_trending", "GitHub Trending Daily (all)", "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"),
    ("geeknews", "GeekNews (feedburner)", "https://feeds.feedburner.com/geeknews-feed"),
    ("geeknews_official", "GeekNews 공식 RSS", "https://news.hada.io/rss/news"),
    ("hackernews_show", "Hacker News: Show HN (points>=20)", "https://hnrss.org/show?points=20"),
    ("hackernews_show_official", "Hacker News 공식 showrss (점수 필터 없음)", "https://news.ycombinator.com/showrss"),
    ("huggingface_blog", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("hackernews_newest", "Hacker News Newest (전체)", "https://hnrss.org/newest"),
    ("devto_ai", "DEV Community #ai", "https://dev.to/feed/tag/ai"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VibePpiyakNewsletterBot/1.0)"}


def measure(src_id: str, name: str, url: str, include_kws: list[str]) -> dict:
    t0 = time.perf_counter()
    retried = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code >= 500:
            retried = resp.status_code
            time.sleep(3)
            t0 = time.perf_counter()
            resp = requests.get(url, headers=HEADERS, timeout=20)
        elapsed = round(time.perf_counter() - t0, 2)
        status = resp.status_code
        feed = feedparser.parse(resp.content)
    except Exception as e:  # 응답 없음도 측정 결과다
        return {"id": src_id, "name": name, "url": url, "status": f"error: {type(e).__name__}", "items": 0}

    entries = feed.entries
    now = datetime.now(timezone.utc)
    n = len(entries)
    oss = rel = fresh = fresh72 = dated = 0
    lengths = []
    for e in entries:
        link = getattr(e, "link", "") or ""
        raw = getattr(e, "summary", "") or getattr(e, "description", "") or ""
        text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        lengths.append(len(text))
        blob = f"{getattr(e, 'title', '')} {text} {link}"
        if "github.com" in blob.lower() or "gitlab.com" in blob.lower():
            oss += 1
        if keyword_hit(f"{getattr(e, 'title', '')} {text}", include_kws):
            rel += 1
        ts = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        if ts:
            dated += 1
            age_h = (now - datetime.fromtimestamp(calendar.timegm(ts), timezone.utc)).total_seconds() / 3600
            if age_h <= 48:
                fresh += 1
            if age_h <= 72:
                fresh72 += 1

    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "id": src_id,
        "name": name,
        "url": url,
        "status": status,
        "retried_after": retried,
        "elapsed_s": elapsed,
        "items": n,
        "oss_url_rate_pct": pct(oss, n),
        "relevance_rate_pct": pct(rel, n),
        "noise_rate_pct": round(100 - pct(rel, n), 1) if n else None,
        "fresh_48h_rate_pct": pct(fresh, dated),
        "fresh_72h_rate_pct": pct(fresh72, dated),
        "dated_items": dated,
        "summary_len_median": int(statistics.median(lengths)) if lengths else 0,
    }


def main() -> None:
    config = yaml.safe_load((ROOT / "audience.yaml").read_text(encoding="utf-8"))
    include_kws = [k for k in config["selection_criteria"]["preliminary"]["include_keywords"]
                   if k not in ("github.com", "open-source", "open source")]
    rows = [measure(*c, include_kws) for c in CANDIDATES]

    out = {"measured_at": datetime.now(timezone.utc).isoformat(), "rows": rows}
    path = ROOT / "store" / "source_measurement.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"측정 시각(UTC): {out['measured_at']}\n")
    print("| 소스 | status | 응답(s) | 건수 | 오픈소스 URL 포함률 | 관련률 | 노이즈율 | 48h 신선도 | 72h 신선도 | 요약 길이 중앙값 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['name']} | {r['status']}{' (재시도 전 ' + str(r['retried_after']) + ')' if r.get('retried_after') else ''} | {r.get('elapsed_s', '-')} | {r['items']} | "
            f"{r.get('oss_url_rate_pct')}% | {r.get('relevance_rate_pct')}% | {r.get('noise_rate_pct')}% | "
            f"{r.get('fresh_48h_rate_pct')}% | {r.get('fresh_72h_rate_pct')}% | {r.get('summary_len_median', '-')} |"
        )


if __name__ == "__main__":
    main()
