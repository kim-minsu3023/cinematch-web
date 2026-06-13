import sys
import os
import threading
import bisect
from datetime import datetime  

# 모듈 탐색 경로 설정 (제일 위에 있어야 함)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, HTTPException
import requests

from database import users_collection, movies_collection
from bson import ObjectId
from pydantic import BaseModel  
from ai_service.model.recommend import get_recommendations

# ✨ AI 자연어 검색을 위해 새로 추가된 라이브러리
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

router = APIRouter()

# .env에 숨겨둔 TMDB API 키 가져오기
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# ✨ 장르 ID를 한글 텍스트로 변환하기 위한 매핑 사전 추가
GENRE_MAP = {
    28: "액션", 12: "모험", 16: "애니메이션", 35: "코미디", 80: "범죄",
    99: "다큐멘터리", 18: "드라마", 10751: "가족", 14: "판타지", 36: "역사",
    27: "공포", 10402: "음악", 9648: "미스터리", 10749: "로맨스", 878: "SF",
    10770: "TV영화", 53: "스릴러", 10752: "전쟁", 37: "서부"
}

# ✨ [추가] 국가 코드(ISO 3166-1) → TMDB 원어 코드(ISO 639-1) 매핑
# 회원가입은 국가코드(KR/US/JP/GB)를 저장하지만, TMDB 필터는 원어 코드(ko/en/ja)를 사용하므로 변환이 필요함
COUNTRY_LANG_MAP = {
    "KR": "ko", "US": "en", "JP": "ja", "GB": "en"
}

# ✨ 종합 추천도(육각형 '종합' 축) 가중치 — 합이 1.0이 되도록 유지하세요.
#    인기도/최신성/평점을 더 중요하게 만들려면 그 값을 키우고 taste/genre를 줄이면 됩니다.
SCORE_WEIGHTS = {
    "taste": 0.30,       # 취향 유사도 (찜한 영화와 닮은 정도)
    "genre": 0.15,       # 장르 적합도
    "rating": 0.20,      # 평점
    "popularity": 0.20,  # 인기도
    "recency": 0.15,     # 최신성
}

# -------------------------------------------------------------
# ✨ [추가] /search/ai 자연어 검색용 TF-IDF 캐시
# DB 전체 영화의 줄거리로 TF-IDF를 "한 번만" 학습해두고 재사용한다.
# 검색할 때는 검색어만 transform 하므로 매우 빠르다.
# 영화 수가 바뀌면(수집으로 늘어나면) 자동으로 다시 학습한다.
# -------------------------------------------------------------
_search_cache = {
    "count": None,        # 캐시를 만든 시점의 영화 개수 (간단한 무효화 기준)
    "vectorizer": None,   # 학습된 TF-IDF 벡터라이저
    "matrix": None,       # 전체 영화 줄거리의 TF-IDF 행렬
    "movies": None,       # 결과 매핑용 영화 메타데이터 리스트
}
_search_lock = threading.Lock()


def _get_search_index():
    """DB 영화 줄거리 TF-IDF 인덱스를 캐시에서 가져오거나 새로 만든다."""
    # count_documents 는 전체 문서를 끌어오지 않아 가볍다 → 변경 감지용으로 사용
    current_count = movies_collection.count_documents({})

    with _search_lock:
        if _search_cache["matrix"] is not None and _search_cache["count"] == current_count:
            return _search_cache["vectorizer"], _search_cache["matrix"], _search_cache["movies"]

        # 캐시 미스 → 이때만 전체 영화를 가져와 TF-IDF 학습
        movies = list(movies_collection.find({}, {"_id": 0}))
        overviews = [m.get("overview", "") for m in movies]

        vectorizer = TfidfVectorizer()
        matrix = None
        if overviews:
            try:
                matrix = vectorizer.fit_transform(overviews)
            except ValueError:
                matrix = None  # 데이터가 거의 없을 때 방지

        _search_cache.update({
            "count": current_count,
            "vectorizer": vectorizer,
            "matrix": matrix,
            "movies": movies,
        })
        return vectorizer, matrix, movies


class LikeMovieRequest(BaseModel):
    email: str  # 찜하기를 하는 유저의 이메일

@router.post("/like/{movie_id}")
def like_movie(movie_id: int, request: LikeMovieRequest): 
    result = users_collection.update_one(
        {"email": request.email},
        {"$addToSet": {"liked_movies": movie_id}} # 중복 없이 추가
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    return {"message": "찜 완료!"}

# [추가] 찜 취소 API (MongoDB에서 $pull로 제거)
@router.post("/unlike/{movie_id}")
def unlike_movie(movie_id: int, request: LikeMovieRequest):
    result = users_collection.update_one(
        {"email": request.email},
        {"$pull": {"liked_movies": movie_id}} # 리스트에서 해당 ID 삭제
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    return {"message": "찜 취소 완료!"}

# [추가] 유저가 찜한 영화 ID 목록만 가져오는 API (버튼 ON/OFF 시각화용)
@router.get("/liked-ids/{email}")
def get_liked_movie_ids(email: str):
    user = users_collection.find_one({"email": email})
    if not user or "liked_movies" not in user:
        return []
    return user["liked_movies"]

# ✨ [복구됨] 마이페이지에서 찜한 영화 포스터와 상세 목록을 가져오는 API
@router.get("/mypage/likes/{email}")
def get_liked_movies(email: str):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    user = users_collection.find_one({"email": email})
    
    if not user or "liked_movies" not in user:
        return []

    liked_movie_ids = user["liked_movies"]
    movies_data = []

    for movie_id in liked_movie_ids:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ko-KR"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                movies_data.append({
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "rating": data.get("vote_average", 0),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}",
                    "overview": data.get("overview")
                })
        except Exception as e:
            print(f"영화 ID {movie_id} 가져오기 실패: {str(e)}")
            continue 

    return movies_data

# -------------------------------------------------------------
# ✨ [추가 옵션 1 적용] 영화 상세 정보 API 
# (OTT 정보 및 프론트엔드 표출용 포스터 포함 추천 배열 추가)
# -------------------------------------------------------------
@router.get("/details/{movie_id}")
def get_movie_details(movie_id: int):
    # 1. 기본 영화 상세 정보 호출
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits,videos,reviews,release_dates"
    data = requests.get(url).json()
    
    director = next((c["name"] for c in data.get("credits", {}).get("crew", []) if c["job"] == "Director"), "알 수 없음")
    cast = [actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]]

    trailer_key = next((v["key"] for v in data.get("videos", {}).get("results", []) 
                        if v["type"] == "Trailer" and v["site"] == "YouTube"), None)
    
    reviews = [{"author": r["author"], "content": r["content"][:200]} 
               for r in data.get("reviews", {}).get("results", [])[:2]]

    age_rating = "등급 미정"
    for item in data.get("release_dates", {}).get("results", []):
        if item.get("iso_3166_1") == "KR":
            dates = item.get("release_dates", [])
            if dates and dates[0].get("certification"):
                cert = dates[0].get("certification")
                if cert == "18":
                    age_rating = "청소년관람불가"
                elif cert == "15":
                    age_rating = "15세관람가"
                elif cert == "12":
                    age_rating = "12세관람가"
                elif cert in ["All", "ALL"]:
                    age_rating = "전체관람가"
                else:
                    age_rating = cert
            break

    # ✨ 상영 중 여부 판단 (개봉일 기준 45일 이내)
    is_playing_in_theater = False
    release_date_str = data.get("release_date", "")
    if release_date_str:
        try:
            # 문자열 날짜를 datetime 객체로 변환
            release_date_obj = datetime.strptime(release_date_str, "%Y-%m-%d")
            # 오늘 날짜와의 차이 계산
            days_diff = (datetime.now() - release_date_obj).days
            # 미래에 개봉하거나(음수) 개봉한 지 45일 이내라면 상영 중으로 판단
            if days_diff <= 45:
                is_playing_in_theater = True
        except ValueError:
            pass

    # 2. [추가] 시청 가능한 OTT 정보 호출 (한국 기준)
    ott_url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={TMDB_API_KEY}"
    ott_data = requests.get(ott_url).json()
    kr_providers = []
    
    if "results" in ott_data and "KR" in ott_data["results"]:
        if "flatrate" in ott_data["results"]["KR"]: # 정액제 서비스만 추출
            for provider in ott_data["results"]["KR"]["flatrate"]:
                kr_providers.append({
                    "provider_name": provider.get("provider_name"),
                    "logo_path": provider.get("logo_path")
                })

    # 3. [수정] AI 연쇄 추천을 위한 Pool 생성 (프론트용 포스터 URL 추가!)
    popular_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=ko-KR&page=1"
    popular_data = requests.get(popular_url).json()
    movie_list = [{
        "id": m['id'], 
        "title": m['title'], 
        "overview": m['overview'],
        "poster_url": f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get("poster_path") else ""
    } for m in popular_data['results']]
    
    if not any(m['id'] == movie_id for m in movie_list):
        target_movie = {
            "id": movie_id,
            "title": data.get("title", ""),
            "overview": data.get("overview", ""),
            "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else ""
        }
        movie_list.append(target_movie)

    # 4. [수정] 자체 추천 엔진 실행 후, 화면 하단 표시용 6개 추출 및 포스터 매핑
    raw_recommendations = get_recommendations(movie_list, movie_id)
    final_recommendations = []
    for rec in raw_recommendations[:6]: # 최대 6개까지만
        rec_detail = next((m for m in movie_list if m['id'] == rec['id']), None)
        if rec_detail:
            final_recommendations.append(rec_detail)

    return {
        "title": data.get("title"),
        "overview": data.get("overview"),
        "director": director,
        "cast": ", ".join(cast),
        "release_date": data.get("release_date", "정보 없음"),
        "genres": [g["name"] for g in data.get("genres", [])],
        "vote_average": data.get("vote_average", 0),
        "trailer_key": trailer_key,      
        "reviews": reviews,              
        "recommendations": final_recommendations, 
        "age_rating": age_rating,
        "ott_providers": kr_providers,             
        "is_playing_in_theater": is_playing_in_theater 
    }

@router.get("/home-sections")
def get_home_sections():
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    # 할리우드/애니: 인기순 + 2021년 이후 + 평가수 100개 이상 (이쪽은 평가가 충분해서 잘 동작)
    popular_filter = "primary_release_date.gte=2021-01-01&sort_by=popularity.desc&vote_count.gte=100&include_adult=false"

    # ✨ 국내 영화: '평가 수'가 아니라 '한국 극장 개봉작'을 기준으로 거른다.
    #   - region=KR + release_date.gte : 한국에서 개봉한 영화로 필터 (TMDB는 이 조합이어야 지역 필터가 먹힘)
    #   - with_release_type=3|2 (%7C=|) : 극장 개봉작만 → VOD 전용 비주류/성인물 제외
    #   - vote_count.gte=10 : 데이터가 거의 없는 것만 살짝 거름 (최신작도 나오도록 낮게 설정)
    ko_url = (
        f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR"
        f"&with_original_language=ko&region=KR&release_date.gte=2024-01-01"
        f"&with_release_type=3%7C2&sort_by=popularity.desc&vote_count.gte=10&include_adult=false&page=1"
    )
    en_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&with_original_language=en&{popular_filter}&page=1"
    ani_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&with_genres=16&{popular_filter}&page=1"

    try:
        def fetch_movies(url):
            response = requests.get(url)
            data = response.json()
            
            movies = []
            for item in data.get('results', [])[:15]:
                movies.append({
                    "id": item['id'],
                    "title": item['title'],
                    "rating": item['vote_average'],
                    "poster_url": f"https://image.tmdb.org/t/p/w500{item['poster_path']}",
                    "overview": item['overview']
                })
            return movies

        return {
            "korean": fetch_movies(ko_url),
            "foreign": fetch_movies(en_url),
            "animation": fetch_movies(ani_url)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"TMDB 연결 실패: {str(e)}")
    
# -------------------------------------------------------------
# 유저 맞춤 AI 추천 API
# -------------------------------------------------------------
@router.get("/recommendations/personal/{email}")
def get_personal_recommendations(email: str):
    """유저의 찜 목록을 기반으로 AI 맞춤 추천 영화를 반환하는 API (MongoDB 기반)"""
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    user = users_collection.find_one({"email": email})
    if not user or not user.get("liked_movies"):
        return {"movies": [], "genre": ""} 

    liked_movie_ids = user["liked_movies"]
    target_movie_id = liked_movie_ids[-1] 

    all_movies_cursor = movies_collection.find({}, {"_id": 0}) 
    movie_list = list(all_movies_cursor)

    target_movie = next((m for m in movie_list if m['id'] == target_movie_id), None)
    
    target_genre = "명작" 
    if target_movie and target_movie.get('genre_ids'):
        main_genre_id = target_movie['genre_ids'][0]
        target_genre = GENRE_MAP.get(main_genre_id, "명작")

    if not target_movie:
        target_url = f"https://api.themoviedb.org/3/movie/{target_movie_id}?api_key={TMDB_API_KEY}&language=ko-KR"
        try:
            target_data = requests.get(target_url).json()
            target_movie = {
                "id": target_movie_id,
                "title": target_data.get("title", ""),
                "overview": target_data.get("overview", "")
            }
            movie_list.append(target_movie)
        except Exception:
            return {"movies": [], "genre": ""} 

    # 후보를 넉넉히 받아온 뒤, 찜한 영화들의 '주 언어'와 같은 영화를 우선 노출하도록 재정렬한다.
    raw_recommendations = get_recommendations(movie_list, target_movie_id, top_n=200)

    # 영화 id → 정보 매핑 (DB에서 직접 읽어 캐시 영향 없음)
    movie_by_id = {m["id"]: m for m in movie_list}
    lang_by_id = {mid: m.get("original_language") for mid, m in movie_by_id.items()}

    # ✨ 저품질·소수 투표 영화 거르기 (예: 1~2표로 평점 10.0인 '섹귀'·'과외누나' 류 제외)
    MIN_VOTE_COUNT = 100  # 추천 단계 2차 필터: 평가 수 100 미만은 추천에서 제외(수집은 50, 추천은 100)
    def is_quality(mid):
        m = movie_by_id.get(mid, {})
        vc = m.get("vote_count")
        if vc is not None:                      # 투표 수 정보가 있으면 그것으로 판단
            return vc >= MIN_VOTE_COUNT
        return m.get("vote_average", 0) < 9.3   # 없으면(재수집 전) 평점 이상치로 임시 판단

    # 찜한 영화들의 가장 많은 언어 = 선호 언어 (예: 한국 영화만 찜했으면 'ko')
    liked_langs = [lang_by_id.get(mid) for mid in liked_movie_ids if lang_by_id.get(mid)]
    pref_lang = max(set(liked_langs), key=liked_langs.count) if liked_langs else None

    # 찜한 영화·저품질 영화 제외 후 (선호 언어 우선 → 그다음 유사도순)으로 정렬
    candidates = [r for r in raw_recommendations
                  if r["id"] not in liked_movie_ids and is_quality(r["id"])]
    candidates.sort(
        key=lambda r: (
            1 if (pref_lang and lang_by_id.get(r["id"]) == pref_lang) else 0,
            r.get("final_score", 0)
        ),
        reverse=True
    )

    final_recommendations = []
    for rec in candidates:
        final_recommendations.append({
            "id": rec.get("id"),
            "title": rec.get("title"),
            "rating": rec.get("vote_average", 0),
            "poster_url": rec.get("poster_url", ""),
            "overview": rec.get("overview", "")
        })
        if len(final_recommendations) >= 10:
            break

    return {
        "movies": final_recommendations,
        "genre": target_genre
    }

# -------------------------------------------------------------
# ✨ [신규] 선호 장르/국가 기반 메인화면 추천 API
# 회원가입 때 선택한 preferred_genres / preferred_countries 를 읽어
# TMDB discover 로 "선호 장르 중 하나라도 포함 + 선호 국가" 영화를 추천한다.
# -------------------------------------------------------------
@router.get("/recommendations/preferences/{email}")
def get_preference_recommendations(email: str):
    """회원가입 때 선택한 선호 장르/국가를 기반으로 메인화면 추천 영화를 반환하는 API"""
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    genre_ids = user.get("preferred_genres", []) or []
    country_codes = user.get("preferred_countries", []) or []

    # 장르는 OR 조건으로 묶는다 (%7C = '|' : 선택한 장르 중 하나라도 포함하면 추천)
    genre_param = "%7C".join(str(g) for g in genre_ids)

    # 선택한 국가들을 TMDB 원어 코드로 변환 (중복 제거)
    langs = []
    for c in country_codes:
        lang = COUNTRY_LANG_MAP.get(c)
        if lang and lang not in langs:
            langs.append(lang)

    # 공통 필터: 인기순 + 최소 평점 수 50개 이상(허접한 영화 제외)
    base = (
        f"https://api.themoviedb.org/3/discover/movie"
        f"?api_key={TMDB_API_KEY}&language=ko-KR"
        f"&sort_by=popularity.desc&vote_count.gte=50"
    )
    if genre_param:
        base += f"&with_genres={genre_param}"

    # 국가가 있으면 국가(언어)별로 각각 조회, 없으면 한 번만 조회
    urls = [base + f"&with_original_language={l}" for l in langs] if langs else [base]

    collected = {}  # id를 키로 사용해 중복 제거
    try:
        for url in urls:
            res = requests.get(url).json()
            for item in res.get("results", []):
                if not item.get("poster_path"):
                    continue
                mid = item["id"]
                if mid in collected:
                    continue
                collected[mid] = {
                    "id": mid,
                    "title": item["title"],
                    "rating": item.get("vote_average", 0),
                    "poster_url": f"https://image.tmdb.org/t/p/w500{item['poster_path']}",
                    "overview": item.get("overview", ""),
                    "_pop": item.get("popularity", 0)  # 내부 정렬용
                }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"TMDB 연결 실패: {str(e)}")

    # 여러 국가 결과를 인기순으로 합쳐서 상위 15개 추출
    movies = sorted(collected.values(), key=lambda m: m["_pop"], reverse=True)[:15]
    for m in movies:
        m.pop("_pop", None)  # 내부 정렬용 필드는 응답에서 제거

    # 프론트 제목에 활용할 선호 장르 이름들
    genre_names = [GENRE_MAP.get(g, "") for g in genre_ids if GENRE_MAP.get(g)]

    return {
        "movies": movies,
        "genres": genre_names
    }

# -------------------------------------------------------------
# ✨ [신규] 추천 영화 ↔ 내 취향 일치도 (육각형 레이더 시각화용)
# 추천 영화 한 편이 내 취향에 얼마나 맞는지 6개 축(0~100) 점수로 반환한다.
#   1) 취향 유사도 : 찜한 영화들과의 평균 줄거리 유사도(TF-IDF)
#   2) 장르 적합도 : 선호 장르 + 찜한 영화 장르와의 겹침
#   3) 평점        : vote_average 환산
#   4) 인기도      : DB 내 popularity 백분위
#   5) 최신성      : 개봉 연도 기준(최근일수록 높음)
#   6) 종합 추천도 : 취향유사도*0.8 + 평점*0.2 (추천 엔진과 동일 가중치)
# -------------------------------------------------------------
@router.get("/recommendations/match/{email}/{movie_id}")
def get_recommendation_match(email: str, movie_id: int):
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")

    liked_movie_ids = user.get("liked_movies", []) or []
    preferred_genres = set(user.get("preferred_genres", []) or [])

    # DB 전체 영화 풀 (추천 엔진과 같은 목록이라 캐시를 공유한다)
    movie_list = list(movies_collection.find({}, {"_id": 0}))
    if not movie_list:
        raise HTTPException(status_code=404, detail="영화 데이터가 없습니다.")

    # 대상 영화가 DB에 없으면 TMDB에서 가져와 풀에 추가
    target = next((m for m in movie_list if m.get("id") == movie_id), None)
    if target is None:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ko-KR"
        try:
            d = requests.get(url).json()
            target = {
                "id": movie_id,
                "title": d.get("title", ""),
                "overview": d.get("overview", ""),
                "vote_average": d.get("vote_average", 0),
                "popularity": d.get("popularity", 0),
                "release_date": d.get("release_date", ""),
                "genre_ids": [g["id"] for g in d.get("genres", [])],
            }
            movie_list.append(target)
        except Exception:
            raise HTTPException(status_code=404, detail="영화 정보를 가져올 수 없습니다.")

    # 1) 취향 유사도 — 추천 엔진을 재사용해 찜한 영화들과의 유사도 계산
    taste_sim = 0.0  # 0~1
    matched_likes = 0  # 찜 영화 중 DB에서 실제 비교에 사용된 개수 (디버깅용)
    if liked_movie_ids:
        # 대상 영화 기준 전체 유사도를 받아 찜한 영화들 것만 추출
        recs = get_recommendations(movie_list, movie_id, top_n=len(movie_list))
        sim_by_id = {r["id"]: r.get("similarity", 0) for r in recs}
        liked_sims = [sim_by_id[mid] for mid in liked_movie_ids if mid in sim_by_id]
        matched_likes = len(liked_sims)
        if liked_sims:
            # ✨ '평균'이 아니라 '가장 비슷한 찜 영화'와의 유사도(최댓값)를 사용한다.
            #    취향이 다양하면 평균은 0에 수렴하므로, 최댓값이 "이건 네가 좋아한 ○○와 닮았어"를 더 잘 표현한다.
            taste_sim = max(liked_sims)

    # 2) 장르 적합도 — 선호 장르(가입) + 찜한 영화들의 장르를 합친 집합과 비교
    pref_set = set(preferred_genres)
    for m in movie_list:
        if m.get("id") in liked_movie_ids:
            pref_set.update(m.get("genre_ids", []) or [])
    movie_genres = target.get("genre_ids", []) or []
    if movie_genres and pref_set:
        matched = len([g for g in movie_genres if g in pref_set])
        genre_fit = matched / len(movie_genres)
    else:
        genre_fit = 0.0

    # 3) 평점
    vote = float(target.get("vote_average", 0) or 0)
    rating_score = min(vote / 10.0, 1.0)

    # 4) 인기도 — DB 내 백분위 (이상치에 강하고 0~1로 떨어짐)
    pops = sorted(float(m.get("popularity", 0) or 0) for m in movie_list)
    target_pop = float(target.get("popularity", 0) or 0)
    rank = bisect.bisect_right(pops, target_pop)
    popularity_score = (rank / len(pops)) if pops else 0.0

    # 5) 최신성 — 매년 5%씩 감소, 20년 지나면 0
    recency = 0.0
    rd = target.get("release_date", "") or ""
    if len(rd) >= 4 and rd[:4].isdigit():
        age = datetime.now().year - int(rd[:4])
        recency = min(max(0.0, 1.0 - age * 0.05), 1.0)

    # 6) 종합 추천도 — 5개 요소의 가중 평균 (가중치는 맨 위 SCORE_WEIGHTS에서 조절)
    w = SCORE_WEIGHTS
    final_score = (
        taste_sim * w["taste"]
        + genre_fit * w["genre"]
        + rating_score * w["rating"]
        + popularity_score * w["popularity"]
        + recency * w["recency"]
    )

    def pct(x):
        return round(x * 100)

    return {
        "movie_id": movie_id,
        "title": target.get("title", ""),
        "overall": pct(final_score),
        # 프론트에서 그대로 레이더 축으로 사용 (순서 = 그리는 순서)
        "scores": {
            "취향 유사도": pct(taste_sim),
            "장르 적합도": pct(genre_fit),
            "평점": pct(rating_score),
            "인기도": pct(popularity_score),
            "최신성": pct(recency),
            "종합 추천도": pct(final_score),
        },
        "has_likes": bool(liked_movie_ids),
        "matched_likes": matched_likes,
    }

# -------------------------------------------------------------
# 🔍 1. 일반 영화 제목 검색 API
# -------------------------------------------------------------
@router.get("/search/title")
def search_by_title(query: str):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")
        
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&language=ko-KR&query={query}&page=1"
    response = requests.get(search_url).json()
    
    results = []
    for item in response.get("results", [])[:10]: # 10개만 추출
        if item.get("poster_path"): # 포스터가 있는 영화만
            results.append({
                "id": item['id'],
                "title": item['title'],
                "rating": item['vote_average'],
                "poster_url": f"https://image.tmdb.org/t/p/w500{item['poster_path']}",
                "overview": item['overview']
            })
    return results

# -------------------------------------------------------------
# 🤖 2. 슬래시(/) AI 자연어 추천 검색 API (TF-IDF 벡터 유사도)
# -------------------------------------------------------------
@router.get("/search/ai")
def search_by_ai(query: str):
    # 1. 캐시된 TF-IDF 인덱스 가져오기 (전체 영화는 한 번만 학습됨)
    vectorizer, matrix, movies = _get_search_index()
    if matrix is None or not movies:
        return []

    # 2. 검색어만 그때그때 벡터로 변환 (학습은 안 하고 변환만 → 빠름)
    try:
        query_vec = vectorizer.transform([query])
    except ValueError:
        return []

    # 3. 검색어 vs 전체 영화 줄거리 유사도 계산
    cosine_sim = cosine_similarity(query_vec, matrix).flatten()

    # 4. 유사도가 가장 높은 상위 10개 영화 추출
    top_indices = cosine_sim.argsort()[-10:][::-1]

    results = []
    for i in top_indices:
        if cosine_sim[i] > 0.01:  # 유사도가 조금이라도 있는 것만
            # DB에는 poster_url 이 통째로 저장돼 있으므로 그대로 사용,
            # (혹시 옛 데이터에 poster_path 만 있으면 URL을 조립)
            poster_url = movies[i].get("poster_url", "")
            if not poster_url:
                poster_path = movies[i].get("poster_path", "")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

            results.append({
                "id": movies[i]['id'],
                "title": movies[i]['title'],
                "rating": movies[i].get('vote_average', 0),
                "poster_url": poster_url,
                "overview": movies[i].get('overview', '')
            })

    return results