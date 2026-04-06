"""
Biz-Flow 데이터 파이프라인
기업마당 OpenAPI로 공고 수집 → Gemini 1.5 Flash로 AI 분석 → policies.json 저장
"""

import requests
import json
import os
import re
import time
import google.generativeai as genai
from datetime import datetime, date

# ── API 키 (GitHub Secrets에서 주입) ─────────────────
BIZINFO_API_KEY = os.environ.get("BIZINFO_API_KEY", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")

# ── 출력 경로: 스크립트 위치 기준 web_app/assets/data/ ─
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(_SCRIPT_DIR, "..", "web_app", "public", "data", "policies.json")

# ── Gemini 초기화 ────────────────────────────────────
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    model = None


# ──────────────────────────────────────────────────────
#  Step 1: 기업마당 OpenAPI 호출
# ──────────────────────────────────────────────────────
def fetch_bizinfo_data(max_pages: int = 3) -> list[dict]:
    """기업마당 공고 목록을 여러 페이지 수집합니다."""
    all_items = []
    for page in range(1, max_pages + 1):
        url = (
            "https://www.bizinfo.go.kr/openapi/v1/selectSupportProjectList"
            f"?crtfcKey={BIZINFO_API_KEY}&dataType=json&pageIndex={page}&pageUnit=10"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                break
            all_items.extend(items)
            print(f"[BizInfo] 페이지 {page}: {len(items)}건 수집")
        except Exception as e:
            print(f"[BizInfo] 오류 (페이지 {page}): {e}")
            break
    return all_items


# ──────────────────────────────────────────────────────
#  Step 2: Gemini AI 처리
# ──────────────────────────────────────────────────────
def process_with_ai(title: str, content: str) -> dict:
    """
    공고 제목/내용을 AI로 분석합니다.
    반환: {"is_loan": bool, "summary": str, "cert_bonus": str|None}
    """
    prompt = f"""
다음 정부지원사업 공고를 분석해서 JSON 형식으로만 답해줘.

제목: {title}
내용: {content[:1500]}

출력 형식 (JSON만, 설명 없이):
{{
    "is_loan": boolean (융자/대출이면 true, 보조금/바우처면 false),
    "summary": "핵심 내용 1줄 요약 (갚지 않아도 되는 돈인지 반드시 명시, 50자 이내)",
    "cert_bonus": "벤처기업인증/ISO인증 등 가점 인증명, 없으면 null"
}}
"""
    if model is None:
        return {"is_loan": False, "summary": content[:80].strip(), "cert_bonus": None}

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        # 마크다운 코드 블록 제거
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        result = json.loads(raw)
        time.sleep(1.2)  # 무료 티어 Rate Limit 준수
        return {
            "is_loan":    bool(result.get("is_loan", False)),
            "summary":    str(result.get("summary", "")),
            "cert_bonus": result.get("cert_bonus") or None,
        }
    except json.JSONDecodeError:
        print(f"  ⚠ JSON 파싱 실패: {title[:30]}")
        return {"is_loan": False, "summary": content[:80].strip(), "cert_bonus": None}
    except Exception as e:
        print(f"  ❌ Gemini 오류: {e}")
        return {"is_loan": False, "summary": content[:80].strip(), "cert_bonus": None}


# ──────────────────────────────────────────────────────
#  Step 3: 데이터 변환 · 병합 · 저장
# ──────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(f"🚀 Biz-Flow 파이프라인 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # ① 기존 수동 입력 데이터 로드 (id가 'api_'로 시작하지 않는 항목 보존)
    existing_manual: list[dict] = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_manual = [p for p in existing if not str(p.get("id", "")).startswith("api_")]
        print(f"[기존 데이터] 수동 항목 {len(existing_manual)}건 보존")

    # ② 신규 API 데이터 수집
    new_items: list[dict] = []
    if BIZINFO_API_KEY:
        raw_data = fetch_bizinfo_data(max_pages=3)
        today = date.today().isoformat()

        for i, item in enumerate(raw_data[:15]):  # 하루 최대 15건 처리
            title   = item.get("title",   "제목 없음")
            content = item.get("content", "")
            deadline = item.get("deadline", "")

            # 마감 지난 항목 스킵
            if deadline and deadline < today:
                continue

            print(f"\n  🔍 [{i+1}] AI 분석 중: {title[:40]}")
            ai = process_with_ai(title, content)

            new_items.append({
                "id":        f"api_{i:04d}",
                "title":     title,
                "deadline":  deadline or None,
                "is_loan":   ai["is_loan"],
                "summary":   ai["summary"],
                "cert_bonus": ai["cert_bonus"],
                "url":       item.get("link", "https://www.bizinfo.go.kr"),
            })
            print(f"     → {'[융자]' if ai['is_loan'] else '[보조금]'} {ai['summary'][:40]}")
    else:
        print("[경고] BIZINFO_API_KEY 미설정 → API 수집 건너뜀")

    # ③ 병합 (수동 데이터 + 신규 API 데이터)
    merged = existing_manual + new_items

    # ④ D-Day 기준 정렬 (마감 없는 항목은 맨 뒤)
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
