import os
import requests
import time
import sys
import dns.resolver  # ✨ DNS 모듈 추가

# ✨ [핵심 해결책] 구글 DNS(8.8.8.8)를 강제로 사용하도록 설정합니다.
# 이 설정을 통해 Mac 환경 등에서 발생하는 'no nameservers' 에러를 방지합니다.
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

# 상위 폴더의 database.py를 불러오기 위한 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import movies_collection  # 미리 만들어두셨던 movies_collection 활성화!

# .env 파일 로드 (python-dotenv가 설치되어 있다고 가정)
from dotenv import load_dotenv
load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")


def collect_movies_to_db(max_pages=500, sort_by="popularity.desc", extra_params=""):
    """
    TMDB discover 로 영화를 가져와 MongoDB에 upsert(있으면 갱신, 없으면 추가) 합니다.

    ⚠️ TMDB는 '한 쿼리당 최대 500페이지(약 1만 개)'까지만 응답합니다.
       501페이지 이상은 에러로 거부되므로 그 이상은 가져올 수 없습니다.
       대신 sort_by(정렬 기준)를 바꿔가며 여러 번 호출하면 서로 다른 영화들이
       더 많이 모이고, 중복은 upsert(id 기준)로 자동 제거됩니다.
    """
    if not TMDB_API_KEY:
        print("🚨 TMDB API 키를 찾을 수 없습니다.")
        return 0, 0

    print(f"🚀 [{sort_by}] 최대 {max_pages}페이지 수집 시작...")
    inserted = 0
    updated = 0

    for page in range(1, max_pages + 1):
        url = (
            f"https://api.themoviedb.org/3/discover/movie"
            f"?api_key={TMDB_API_KEY}&language=ko-KR"
            f"&sort_by={sort_by}{extra_params}&page={page}"
        )

        try:
            response = requests.get(url)
            if response.status_code != 200:
                # 501페이지 이상이거나 일시 오류면 TMDB가 200이 아닌 응답을 준다 → 이 정렬 기준 종료
                print(f"❌ {page}페이지 응답코드 {response.status_code} → [{sort_by}] 수집 종료")
                break

            movies = response.json().get('results', [])

            for m in movies:
                # 줄거리가 없는 영화는 AI 유사도 분석이 불가능하므로 제외
                if not m.get('overview'):
                    continue

                movie_data = {
                    "id": m['id'],
                    "title": m['title'],
                    "overview": m['overview'],
                    "release_date": m.get('release_date', ''),
                    "vote_average": m.get('vote_average', 0),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get('poster_path') else "",
                    "genre_ids": m.get('genre_ids', []),
                    "popularity": m.get('popularity', 0),
                    "original_language": m.get('original_language', '')  # ✨ 원어(ko/en/ja...) — 언어 기반 추천용
                }

                # upsert=True : 같은 id가 있으면 갱신, 없으면 새로 추가 (중복 자동 제거)
                result = movies_collection.update_one(
                    {"id": m['id']},
                    {"$set": movie_data},
                    upsert=True
                )

                if result.upserted_id:
                    inserted += 1
                elif result.modified_count > 0:
                    updated += 1

            # TMDB 서버에 무리가 가지 않도록 페이지마다 살짝 쉬어주기
            time.sleep(0.1)

            if page % 50 == 0:
                print(f"⏳ [{sort_by}] {page}페이지 완료... (신규 {inserted} / 갱신 {updated})")

        except Exception as e:
            print(f"🚨 에러 발생 ({page}페이지): {str(e)}")

    print(f"✅ [{sort_by}] 완료 — 신규 {inserted}개 / 갱신 {updated}개")
    return inserted, updated


if __name__ == "__main__":
    # 여러 정렬 기준으로 모으면 한 쿼리(1만 개) 한계를 넘겨 더 많은 영화를 수집한다.
    # (인기순 외에 평가수·수익·최신·평점순으로 서로 다른 영화들이 잡힘. 중복은 upsert로 자동 제거)
    # - 평점순(vote_average)은 평가수 필터를 걸어야 허접한 영화가 안 섞인다.
    queries = [
        ("popularity.desc", ""),                              # 인기순
        ("vote_count.desc", ""),                              # 평가 많은 순
        ("revenue.desc", ""),                                 # 흥행 수익 순
        ("primary_release_date.desc", "&vote_count.gte=30"),  # 최신순(평가 30개 이상)
        ("vote_average.desc", "&vote_count.gte=300"),         # 평점 높은 순(평가 300개 이상)
    ]

    total_new = 0
    for sort_by, extra in queries:
        print(f"\n===== 정렬 기준: {sort_by} =====")
        new, upd = collect_movies_to_db(max_pages=500, sort_by=sort_by, extra_params=extra)
        total_new += new

    print("\n🎉 전체 수집 완료!")
    print(f"📊 이번에 새로 추가된 영화: 약 {total_new}개")
    print(f"📊 현재 DB에 저장된 총 영화 수: {movies_collection.count_documents({})}개")