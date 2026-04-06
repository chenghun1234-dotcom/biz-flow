"""
Biz-Flow 데이터 파이프라인
기업마당(Bizinfo) HTML 크롤링 → Gemini 1.5 Flash AI 분석 → policies.json 저장
API 키 없이 Zero-Auth 방식으로 운영. GEMINI_API_KEY만 필요.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
import google.generativeai as genai
from datetime import datetime, date

# ── Gemini API 키 (GitHub Secrets에서 주입) ───────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── 출력 경로: 스크립트 위치 기준 web_app/public/data/ ─
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(_SCRIPT_DIR, "..", "web_app", "public", "data", "policies.json")

# ── Gemini 초기화 ────────────────────────────────────
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    model = None


# ──────────────────────────────────────────────────────
#  Step 1: 기업마당 HTML 크롤링 (Zero-Auth)
# ──────────────────────────────────────────────────────
BIZINFO_LIST_URL = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do"
BIZINFO_BASE_URL = "https://www.bizinfo.go.kr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_bizinfo_data(max_pages: int = 2) -> list[dict]:
    """
    기업마당 지원사업 공고 목록 페이지를 크롤링합니다.
    API 키·회원가입 없이 HTML만 파싱합니다.
    """
    all_items: list[dict] = []

    for page in range(1, max_pages + 1):
        params = {"pageIndex": page}
        try:
            resp = requests.get(BIZINFO_LIST_URL, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[크롤링] 페이지 {page} 요청 실패: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # 첫 번째 <table>의 tbody tr 선택 (클래스 없음 확인됨)
        tables = soup.find_all("table")
        rows = tables[0].select("tbody tr") if tables else []
        if not rows:
            print(f"[크롤링] 페이지 {page}: 게시글 없음 (마지막 페이지 또는 구조 변경)")
            break

        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 5:
                continue

            # td[2]: 제목 + 링크
            title_el = tds[2].find("a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href  = title_el.get("href", "")
            link  = BIZINFO_BASE_URL + href if href.startswith("/") else href

            # pblancId 파라미터를 ID로 사용
            m_id = re.search(r"pblancId=([^&]+)", href)
            item_id = m_id.group(1) if m_id else re.sub(r"\W+", "_", title[:20])

            # td[1]: 분야 (경영/수출/창업/금융 등)
            biz_field = tds[1].get_text(strip=True)

            # td[3]: 기간 "YYYY-MM-DD ~ YYYY-MM-DD" → 마감일만 추출
            date_raw = tds[3].get_text(strip=True)
            m_date = re.search(r"~\s*(\d{4}-\d{2}-\d{2})", date_raw)
            if m_date:
                deadline = m_date.group(1)
            else:
                # 단일 날짜 or YYYY.MM.DD 포맷 처리
                deadline = re.sub(r"(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", date_raw.split("~")[-1].strip())

            # td[4]: 주관기관/지역
            department = tds[4].get_text(strip=True)
            full_title = f"[{department}] {title}" if department else title

            all_items.append({
                "id":        f"crawl_{item_id}",
                "title":     full_title,
                "content":   title,
                "biz_field": biz_field,   # 기업마당 분류 (AI field 분류에 힌트로 사용)
                "deadline":  deadline,
                "url":       link,
            })

        print(f"[크롤링] 페이지 {page}: {len(rows)}건 수집")
        time.sleep(1.0)  # 서버 부하 방지

    return all_items


def fetch_detail_content(url: str) -> str:
    """
    상세 페이지 본문을 추가로 크롤링합니다.
    실패 시 빈 문자열 반환.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # 본문 영역 — 사이트 구조에 따라 selector 조정
        body = soup.select_one(".view_cont") or soup.select_one("#contents")
        return body.get_text(" ", strip=True)[:2000] if body else ""
    except Exception:
        return ""


# ──────────────────────────────────────────────────────
#  Step 2: Gemini AI 분석
# ──────────────────────────────────────────────────────
def process_with_ai(title: str, content: str, biz_field: str = "") -> dict:
    """
    제목·본문을 Gemini로 분석해 is_loan / target / field / summary / cert_bonus 반환.
    """
    field_hint = f"\n기업마당 분류: {biz_field}" if biz_field else ""
    prompt = f"""
다음 정부지원사업 공고를 분석해서 JSON 형식으로만 답해줘.

제목: {title}
내용: {content[:1500]}{field_hint}

출력 형식 (JSON만, 설명 없이):
{{
    "is_loan": boolean (융자/대출이면 true, 보조금/바우처면 false),
    "target": "소상공인|중소기업|제조업|농업/식품|스타트업/창업 중 가장 적합 (슬래시 포함 원문 그대로)",
    "field": "자금/금융|창업지원|R&D/기술|수출/마케팅|경영지원 중 가장 적합 (수식어 포함 원문 그대로)",
    "summary": "핵심 내용 1줄 요약 (갚지 않아도 되는 돈인지 명시, 50자 이내)",
    "cert_bonus": "벤처기업인증/ISO 등 가점 인증명, 없으면 null"
}}
"""
    if model is None:
        return {"is_loan": False, "target": "중소기업", "field": "경영지원", "summary": content[:80].strip() or title[:80], "cert_bonus": None}

    try:
        response = model.generate_content(prompt)
        raw = re.sub(r"```json\s*|\s*```", "", response.text.strip()).strip()
        result = json.loads(raw)
        time.sleep(1.2)  # Gemini 무료 티어 Rate Limit 준수

        # target 값 정규화
        valid_targets = {'소상공인', '중소기업', '제조업', '농업/식품', '스타트업/창업'}
        raw_target = str(result.get('target', ''))
        if '소상공인' in raw_target:            norm_target = '소상공인'
        elif '중소기업' in raw_target:          norm_target = '중소기업'
        elif '제조' in raw_target:              norm_target = '제조업'
        elif '농업' in raw_target or '식품' in raw_target: norm_target = '농업/식품'
        elif '스타트업' in raw_target or '창업' in raw_target: norm_target = '스타트업/창업'
        else:                                   norm_target = '중소기업'

        # field 값 정규화
        raw_field = str(result.get('field', ''))
        if '금융' in raw_field or '자금' in raw_field: norm_field = '자금/금융'
        elif '창업' in raw_field:             norm_field = '창업지원'
        elif 'R&D' in raw_field or '기술' in raw_field: norm_field = 'R&D/기술'
        elif '수출' in raw_field or '마케팅' in raw_field: norm_field = '수출/마케팅'
        else:                                norm_field = '경영지원'

        return {
            "is_loan":    bool(result.get("is_loan", False)),
            "target":     norm_target,
            "field":      norm_field,
            "summary":    str(result.get("summary", "")),
            "cert_bonus": result.get("cert_bonus") or None,
        }
    except json.JSONDecodeError:
        print(f"  ⚠ JSON 파싱 실패: {title[:30]}")
        return {"is_loan": False, "target": "중소기업", "field": "경영지원", "summary": title[:80], "cert_bonus": None}
    except Exception as e:
        print(f"  ❌ Gemini 오류: {e}")
        return {"is_loan": False, "target": "중소기업", "field": "경영지원", "summary": title[:80], "cert_bonus": None}


# ──────────────────────────────────────────────────────
#  Step 3: 병합 · 정렬 · 저장
# ──────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(f"🚀 Biz-Flow 파이프라인 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # ① 기존 수동 항목 보존 (id가 'crawl_'로 시작하지 않는 항목)
    existing_manual: list[dict] = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_manual = [p for p in existing if not str(p.get("id", "")).startswith("crawl_")]
        print(f"[기존 데이터] 수동 항목 {len(existing_manual)}건 보존")

    # ② 기업마당 크롤링
    raw_data = fetch_bizinfo_data(max_pages=2)
    today = date.today().isoformat()
    new_items: list[dict] = []

    for i, item in enumerate(raw_data[:10]):   # 무료 쿼터 절약: 상위 10건만 AI 처리
        title   = item["title"]
        url     = item["url"]
        deadline = item["deadline"]

        # 이미 마감된 항목 건너뜀
        if re.match(r"\d{4}-\d{2}-\d{2}", deadline) and deadline < today:
            print(f"  ⏭ 마감 지남: {title[:30]}")
            continue

        # 상세 본문 추가 크롤링
        print(f"\n  🔍 [{i+1}] 상세 크롤링 + AI 분석: {title[:40]}")
        content = fetch_detail_content(url)
        biz_field = item.get("biz_field", "")
        ai = process_with_ai(title, content or title, biz_field)

        new_items.append({
            "id":        item["id"],
            "title":     title,
            "deadline":  deadline,
            "is_loan":   ai["is_loan"],
            "target":    ai["target"],
            "field":     ai["field"],
            "summary":   ai["summary"],
            "cert_bonus": ai["cert_bonus"],
            "url":       url,
        })
        print(f"     → {'[융자]' if ai['is_loan'] else '[보조금]'} [{ai['target']}][{ai['field']}] {ai['summary'][:35]}")
        time.sleep(0.8)  # 서버 부하 방지

    # ③ 중복 제거 후 병합 (기존 수동 + 신규 크롤링)
    existing_ids = {p["id"] for p in existing_manual}
    deduped_new = [p for p in new_items if p["id"] not in existing_ids]
    merged = existing_manual + deduped_new

    # ④ 마감일 오름차순 정렬 (마감일 없는 항목은 맨 뒤)
    merged.sort(key=lambda p: p.get("deadline") or "9999-12-31")

    # ⑤ 저장
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료: 총 {len(merged)}건 → {OUTPUT_PATH}")
    print(f"   보조금 {sum(1 for p in merged if not p['is_loan'])}건 | "
          f"융자 {sum(1 for p in merged if p['is_loan'])}건")
    print("=" * 55)


if __name__ == "__main__":
    main()
