"""
CineMatch 일일 DB 갱신 배치
-----------------------------------------------------------------
TMDB에서 인기 영화를 다시 수집해 MongoDB를 갱신한다(upsert).
- 새 영화는 추가되고, 기존 영화는 평점/인기도 등이 업데이트된다.
- cron 등으로 하루 한 번 실행하는 용도.
- 웹 서버와 별개 프로세스로 돌며, DB만 갱신하면 서버 캐시는
  다음 요청 때 자동으로 새 데이터를 반영한다.

수동 실행:   python daily_update.py
"""

import os
import sys
from datetime import datetime

# -----------------------------------------------------------------
# 1) 경로/환경변수 세팅
#    이 스크립트는 backend 폴더 밖(crawler-service)에서 도므로,
#    backend 의 .env 와 모듈들을 명시적으로 찾아준다.
# -----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

# backend/.env 를 명시적 경로로 먼저 로드 (cwd가 어디든 키를 찾도록)
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# backend 폴더를 import 경로에 추가 (database / collect_movies 사용)
sys.path.append(BACKEND_DIR)

# collect_movies 안에 DNS 설정과 수집 함수가 모두 들어 있다.
# (import 시점에 구글 DNS 설정이 적용되고, 함수만 가져온다)
from collect_movies import collect_movies_to_db


def run_daily_update(max_pages: int = 200):
    """
    하루 한 번 도는 갱신 작업.
    max_pages=200 이면 약 4,000개(인기순 상위)를 다시 훑는다.
    인기순 정렬이라 신작/화제작은 앞쪽 페이지에 잡히므로,
    매일 전체(500페이지)를 다 돌 필요 없이 이 정도로 충분하다.
    """
    start = datetime.now()
    print(f"[{start:%Y-%m-%d %H:%M:%S}] 🚀 일일 DB 갱신 시작 (max_pages={max_pages})")

    try:
        collect_movies_to_db(max_pages=max_pages)
        end = datetime.now()
        elapsed = (end - start).total_seconds()
        print(f"[{end:%Y-%m-%d %H:%M:%S}] ✅ 갱신 완료 (소요 {elapsed:.0f}초)")
    except Exception as e:
        end = datetime.now()
        print(f"[{end:%Y-%m-%d %H:%M:%S}] 🚨 갱신 실패: {e}")
        sys.exit(1)  # cron 로그에서 실패를 알아챌 수 있도록 비정상 종료


if __name__ == "__main__":
    # 명령줄에서 페이지 수를 넘기면 그 값으로 실행 (예: python daily_update.py 100)
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    run_daily_update(max_pages=pages)