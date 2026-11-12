
import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://computing.sogang.ac.kr"
LIST_URL = f"{BASE_URL}/ko/community/academicNotice/list"

SEARCH_PARAMS = {
    "num": 1,
    "searchKeyword": "멘토",
    "searchCondition": "ALL",
}

STATE_FILE = Path(__file__).with_name("seen_posts.json")
MAX_PAGES = 10
MAX_SAVED_POSTS = 1000

DETAIL_PATTERN = re.compile(
    r"/ko/community/academicNotice/detail/(\d+)"
)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_page(page):
    """학사공지 검색 결과 페이지 조회"""
    params = SEARCH_PARAMS.copy()
    params["num"] = page

    response = requests.get(
        LIST_URL,
        params=params,
        timeout=30,
        headers={
            "User-Agent": "SogangNoticeMonitor/1.0"
        },
    )
    response.raise_for_status()
    return response.text


def extract_posts(html):
    """HTML에서 공지 상세 링크와 게시글 정보 추출"""
    soup = BeautifulSoup(html, "html.parser")
    posts = {}

    # 상세 페이지를 가리키는 모든 링크를 찾습니다.
    # PC 테이블과 모바일 목록의 중복은 ID로 제거합니다.
    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = DETAIL_PATTERN.search(href)

        if not match:
            continue

        post_id = match.group(1)
        title = link.get_text(" ", strip=True)

        if not title:
            continue

        # 학교 외부 링크는 제외
        url = urljoin(BASE_URL, href)
        if urlparse(url).hostname != "computing.sogang.ac.kr":
            continue

        # 해당 링크를 포함하는 표 행 또는 모바일 목록에서
        # 작성일을 찾습니다.
        container = link.find_parent("tr")

        if container is None:
            container = link.find_parent("li")

        date = ""
        if container:
            content = container.get_text(" ", strip=True)
            date_match = DATE_PATTERN.search(content)
            if date_match:
                date = date_match.group(0)

        posts[post_id] = {
            "id": post_id,
            "title": title,
            "date": date,
            "url": url,
        }

    return posts


def fetch_all_posts():
    """검색 결과를 순회하며 게시글 목록 수집"""
    all_posts = {}

    for page in range(1, MAX_PAGES + 1):
        logger.info("검색 결과 %d페이지 확인 중", page)

        html = fetch_page(page)
        page_posts = extract_posts(html)

        if not page_posts:
            if page == 1:
                # 첫 페이지에서 게시글을 못 찾았다면
                # HTML 변경 가능성이 있으므로 실패 처리
                if re.search(
                    r"(?:전체\s*0\s*건|검색\s*결과가\s*없)",
                    BeautifulSoup(html, "html.parser").get_text(" ", strip=True),
                ):
                    return {}

                raise RuntimeError(
                    "첫 페이지에서 게시글을 추출하지 못했습니다. "
                    "사이트 HTML 구조를 확인하세요."
                )
            break

        new_ids = set(page_posts) - set(all_posts)

        # 사이트가 num 파라미터를 무시하는 경우
        # 동일한 페이지를 계속 수집하지 않도록 방지
        if not new_ids:
            break

        all_posts.update(page_posts)

        time.sleep(0.5)

    logger.info("총 %d개의 게시글 확인", len(all_posts))
    return all_posts


def load_state():
    """이전 실행에서 기록한 ID 불러오기"""
    if not STATE_FILE.exists():
        return None

    with STATE_FILE.open("r", encoding="utf-8") as file:
        state = json.load(file)

    return state


def save_state(post_ids):
    """확인 완료한 게시글 ID 저장"""
    state = {
        "initialized": True,
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "seen_ids": sorted(
            post_ids,
            key=lambda x: int(x),
            reverse=True,
        )[:MAX_SAVED_POSTS],
    }

    temp_file = STATE_FILE.with_suffix(".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)

    temp_file.replace(STATE_FILE)


def send_discord(post=None, test=False):
    """Discord Webhook으로 알림 전송"""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL 환경변수가 없습니다."
        )

    if test:
        payload = {
            "content": "<@981509005547552808> ✅ 서강대학교 학사공지 알리미 연결 테스트 성공!",
            "allowed_mentions": {
                "users": ["981509005547552808"]
            }
        }
    
    else:
        payload = {
            "username": "서강대 학사공지 알리미",
            "content": "<@981509005547552808> 📢 새로운 학사공지가 등록되었습니다!",
            "allowed_mentions": {
                "users": ["981509005547552808"]
            },
            "embeds": [
                {
                    "title": post["title"][:256],
                    "url": post["url"],
                    "description": "멘토 검색 결과에 새로운 공지가 등록되었습니다.",
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "작성일",
                            "value": post["date"] or "확인 필요",
                            "inline": True,
                        }
                    ],
                    "footer": {
                        "text": "서강대학교 소프트웨어융합대학"
                    },
                }
            ],
        }


    # 일시적 실패에 한해 재시도
    for attempt in range(3):
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=20,
        )

        if response.status_code in (200, 204):
            return

        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue

        response.raise_for_status()
        raise RuntimeError(
            f"Discord 알림 실패: HTTP {response.status_code}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Discord 연결만 테스트하고 상태는 변경하지 않음",
    )
    args = parser.parse_args()

    if args.test_webhook:
        send_discord(test=True)
        logger.info("Discord 연결 테스트 성공")
        return

    if not os.environ.get("DISCORD_WEBHOOK_URL"):
        raise RuntimeError("Discord Webhook이 설정되지 않았습니다.")

    current_posts = fetch_all_posts()
    current_ids = set(current_posts)

    state = load_state()

    # 첫 실행: 기존 게시글만 저장하고 알림은 생략
    if state is None or not state.get("initialized", False):
        save_state(current_ids)
        logger.info(
            "초기화 완료: 기존 게시글 %d개를 저장했습니다.",
            len(current_ids),
        )
        return

    seen_ids = set(state.get("seen_ids", []))
    new_ids = current_ids - seen_ids

    if not new_ids:
        logger.info("새로운 공지가 없습니다.")
        save_state(seen_ids)
        return

    logger.info("새로운 공지 %d개 발견", len(new_ids))

    # 오래된 게시글부터 전송
    new_posts = sorted(
        (current_posts[post_id] for post_id in new_ids),
        key=lambda post: int(post["id"]),
    )

    # 한 건씩 전송 성공 후 저장하므로 일부 전송 실패에도
    # 성공한 게시글을 다음 실행에서 다시 보내지 않도록 함
    for post in new_posts:
        send_discord(post)
        logger.info("알림 전송 완료: %s", post["title"])

        seen_ids.add(post["id"])
        save_state(seen_ids)


if __name__ == "__main__":
    main()
