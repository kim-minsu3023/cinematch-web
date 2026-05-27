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
from database import movies_collection # 미리 만들어두셨던 movies_collection 활성화!

# .env 파일 로드 (python-dotenv가 설치되어 있다고 가정)
from dotenv import load_dotenv
load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

def collect_movies_to_db(max_pages=100):
    """
    TMDB에서 영화 데이터를 가져와 MongoDB에 대량으로 저장합니다.
    max_pages=100 이면 약 2,000개, 500이면 약 10,000개의 영화를 수집합니다.
    """
    if not TMDB_API_KEY:
        print("🚨 TMDB API 키를 찾을 수 없습니다.")
        return

    print(f"🚀 총 {max_pages}페이지 데이터 수집을 시작합니다...")
    
    total_inserted = 0
    total_updated = 0

    for page in range(1, max_pages + 1):
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&sort_by=popularity.desc&page={page}"
        
        try:
            response = requests.get(url)
            if response.status_code != 200:
                print(f"❌ {page}페이지 로드 실패: {response.status_code}")
                continue
                
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
                    "popularity": m.get('popularity', 0)
                }

                # ✨ upsert=True : DB에 이미 같은 ID의 영화가 있으면 업데이트, 없으면 새로 추가
                result = movies_collection.update_one(
                    {"id": m['id']}, 
                    {"$set": movie_data}, 
                    upsert=True
                )
                
                if result.upserted_id:
                    total_inserted += 1
                elif result.modified_count > 0:
                    total_updated += 1

            # TMDB 서버에 무리가 가지 않도록 페이지마다 살짝 쉬어주기
            time.sleep(0.1) 
            
            if page % 10 == 0:
                print(f"⏳ {page}페이지 완료... (현재까지 {total_inserted + total_updated}개 처리됨)")

        except Exception as e:
            print(f"🚨 에러 발생 ({page}페이지): {str(e)}")

    print("🎉 데이터 수집 완료!")
    print(f"새로 추가됨: {total_inserted}개 | 업데이트됨: {total_updated}개")


if __name__ == "__main__":
    # 처음엔 테스트로 50페이지(약 1,000개)만 수집해 봅시다. 
    # 잘 들어가면 나중에 500(약 10,000개)으로 늘려서 다시 실행하면 됩니다!
    collect_movies_to_db(max_pages=500)