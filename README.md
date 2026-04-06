# 🚀 Biz-Flow | 맞춤형 지원제도 플랫폼

> 소상공인·중소기업을 위한 **보조금/융자/바우처** 맞춤 필터링 대시보드  
> 운영비 **0원**, 완전 자동화 파이프라인

---

## 📁 프로젝트 구조

```
Biz-Flow/
├── lib/                          # Flutter 앱 소스
│   ├── main.dart                 # 앱 진입점 + GoRouter 설정
│   ├── models/
│   │   └── support_program.dart  # 데이터 모델 (SupportProgram, Enum)
│   ├── theme/
│   │   └── app_theme.dart        # 디자인 시스템 (색상, 폰트, 그림자)
│   ├── services/
│   │   └── data_service.dart     # JSON 로드 & 필터링 로직
│   ├── screens/
│   │   ├── home_screen.dart      # 메인 대시보드
│   │   └── detail_screen.dart    # 지원사업 상세 페이지
│   └── widgets/
│       ├── category_tab_bar.dart # [전체][보조금][융자][바우처] 탭
│       ├── hero_section.dart     # 업종/매출 필터 입력 폼
│       ├── support_card.dart     # 지원제도 카드 (배지 포함)
│       ├── lead_modal.dart       # 가점 상담 리드 수집 모달 💰
│       └── adfit_banner.dart     # 카카오 AdFit 배너 위젯
├── data/
│   └── programs.json             # 지원사업 데이터 (DB 대용)
├── scraper/
│   ├── scraper.py                # 기업마당 API + K-Startup 크롤러
│   ├── ai_processor.py           # Gemini 1.5 Flash AI 분석/분류
│   └── requirements.txt          # Python 의존성
├── web/
│   └── index.html                # Flutter Web 진입점 (AdFit 스크립트)
├── .github/workflows/
│   └── update_data.yml           # GitHub Actions (매일 새벽 4시 자동화)
└── pubspec.yaml
```

---

## ⚡ 빠른 시작

### 1. Flutter Web 로컬 실행
```bash
flutter pub get
flutter run -d chrome
```

### 2. Python 스크래퍼 설정
```bash
cd scraper
pip install -r requirements.txt

# .env 파일 생성
echo "BIZINFO_API_KEY=발급받은_키" > .env
echo "GEMINI_API_KEY=발급받은_키" >> .env

# 수동 실행 (데이터 수집 + AI 분석)
python scraper.py
python ai_processor.py
```

---

## 🔑 환경변수 (GitHub Secrets 설정)

| 변수명 | 설명 | 발급 방법 |
|---|---|---|
| `BIZINFO_API_KEY` | 기업마당 OpenAPI 인증키 | [bizinfo.go.kr](https://www.bizinfo.go.kr) 회원가입 후 신청 |
| `GEMINI_API_KEY` | Google Gemini API 키 | [aistudio.google.com](https://aistudio.google.com) (무료) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Pages 배포 토큰 | Cloudflare 대시보드 > API Tokens |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 계정 ID | Cloudflare 대시보드 > 우측 사이드바 |

---

## 💰 수익 모델

| 채널 | 단가 | 작동 방식 |
|---|---|---|
| **기업 인증 대행 리드** | 리드당 3~10만원 | 상담 신청 폼 → 제휴 컨설팅 업체 전달 |
| **카카오 AdFit** | 노출/클릭 기반 | 정적 페이지 스크립트 삽입 |

---

## 🤖 자동화 파이프라인

```
[매일 새벽 4시 GitHub Actions]
       ↓
[scraper.py] 기업마당 API + K-Startup 크롤링
       ↓
[ai_processor.py] Gemini 1.5 Flash로
  - 보조금/융자/바우처 자동 분류
  - 핵심 요약 생성
  - 가점 인증 추출
       ↓
[data/programs.json] GitHub에 커밋
       ↓
[flutter build web] 정적 사이트 빌드
       ↓
[Cloudflare Pages] 무료 배포 (트래픽 무제한)
```

---

## 🎨 UI 핵심 기능

- **뱃지 구분**: 🟢 `[대출 아님]` (보조금) | 🟠 `[대출]` (융자) | 🔵 `[바우처]`
- **실시간 필터**: 업종 + 매출 규모 선택 시 즉시 카드 필터링
- **D-Day 표시**: 마감 3일 이내 빨간색 경고
- **리드 모달**: 상담 신청 시 성함/연락처/업체명 수집 → 수익 전환
- **반응형**: 모바일/태블릿/데스크톱 모두 최적화
