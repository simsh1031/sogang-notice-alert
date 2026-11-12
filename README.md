# Sogang Notice Alert

서강대학교 소프트웨어융합대학 학사공지에서 `멘토` 관련 공고를 주기적으로 확인하고, 새로운 게시글이 등록되면 Discord로 알림을 보내는 개인용 서비스입니다.

## 주요 기능

- 학사공지의 `멘토` 검색 결과 모니터링
- GitHub Actions를 이용한 30분 간격 자동 확인
- 새로운 게시글 발견 시 Discord Webhook 알림
- 게시글 ID 기반 중복 알림 방지
- 최초 실행 시 기존 게시글 자동 등록 (알림 제외)

## 기술 스택

- **Python** — Requests, BeautifulSoup
- **GitHub Actions** — 자동 실행
- **Discord Webhook** — 알림 전송
- **JSON** — 확인한 게시글 ID 저장

## 프로젝트 구조

```text
.
├── .github/
│   └── workflows/
│       └── monitor.yml
├── monitor.py
├── requirements.txt
└── seen_posts.json
```

## 사용 방법

### 1. Discord Webhook 설정

Discord 채널에서 Webhook URL을 생성한 후, GitHub 저장소의 `Settings → Secrets and variables → Actions`에서 다음 Secret을 등록합니다.

- `DISCORD_WEBHOOK_URL`: Discord Webhook URL

### 2. 자동 실행

GitHub Actions에서 매시 15분과 45분에 공지사항을 확인하도록 설정합니다.

```yaml
schedule:
  - cron: "15,45 * * * *"
```

필요한 경우 `Actions → Sogang Notice Monitor → Run workflow`에서 수동 실행할 수도 있습니다.

### 3. 알림 동작

최초 실행 시 기존 게시글 ID를 `seen_posts.json`에 저장합니다. 이후 실행부터 새로운 게시글 ID가 발견되면 제목, 작성일, 게시글 링크를 Discord로 전송합니다.

## 모니터링 대상

[서강대학교 소프트웨어융합대학 학사공지 — 멘토 검색](https://computing.sogang.ac.kr/ko/community/academicNotice/list?num=1&searchKeyword=%EB%A9%98%ED%86%A0&searchCondition=ALL)

---

GitHub Actions 예약 실행은 GitHub 서버 상황에 따라 지연되거나 누락될 수 있습니다.
