import sys
import os

# 모듈 탐색 경로 설정 (제일 위에 있어야 함)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, HTTPException
import requests

from database import users_collection, movies_collection
from bson import ObjectId
from pydantic import BaseModel  
from ai_service.model.recommend import get_recommendations

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

@router.get("/details/{movie_id}")
def get_movie_details(movie_id: int):
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
                elif cert == "All" or cert == "ALL":
                    age_rating = "전체관람가"
                else:
                    age_rating = cert
            break

    popular_url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=ko-KR&page=1"
    popular_data = requests.get(popular_url).json()
    movie_list = [{"id": m['id'], "title": m['title'], "overview": m['overview']} for m in popular_data['results']]
    
    if not any(m['id'] == movie_id for m in movie_list):
        target_movie = {
            "id": movie_id,
            "title": data.get("title", ""),
            "overview": data.get("overview", "")
        }
        movie_list.append(target_movie)

    recommendations = get_recommendations(movie_list, movie_id)

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
        "recommendations": recommendations,
        "age_rating": age_rating  
    }

@router.get("/home-sections")
def get_home_sections():
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    recent_popular_filter = "primary_release_date.gte=2021-01-01&sort_by=popularity.desc"

    ko_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&with_original_language=ko&{recent_popular_filter}&page=1"
    en_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&with_original_language=en&{recent_popular_filter}&page=1"
    ani_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ko-KR&with_genres=16&{recent_popular_filter}&page=1"

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
# ✨ [수정됨] 유저 맞춤 AI 추천 API (장르 텍스트 추출 기능 추가)
# -------------------------------------------------------------
@router.get("/recommendations/personal/{email}")
def get_personal_recommendations(email: str):
    """유저의 찜 목록을 기반으로 AI 맞춤 추천 영화를 반환하는 API (MongoDB 기반)"""
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="API 키가 설정되지 않았습니다.")

    # 1. 유저 정보 및 찜 목록 확인
    user = users_collection.find_one({"email": email})
    if not user or not user.get("liked_movies"):
        return {"movies": [], "genre": ""} # ✨ 빈 형태 반환 변경

    liked_movie_ids = user["liked_movies"]
    
    # 2. 가장 최근에 찜한 영화를 타겟으로 설정!
    target_movie_id = liked_movie_ids[-1] 

    # 3. 추천 후보군(Pool) 만들기: MongoDB에서 전체 영화 데이터 한 번에 가져오기
    all_movies_cursor = movies_collection.find({}, {"_id": 0}) 
    movie_list = list(all_movies_cursor)

    # 4. 타겟 영화가 DB 안에 있는지 확인
    target_movie = next((m for m in movie_list if m['id'] == target_movie_id), None)
    
    # ✨ 타겟 영화의 메인 장르 추출 로직 추가
    target_genre = "명작" # 기본값
    if target_movie and target_movie.get('genre_ids'):
        main_genre_id = target_movie['genre_ids'][0]
        target_genre = GENRE_MAP.get(main_genre_id, "명작")

    # 에러 방지: 혹시 타겟 영화가 DB에 없는 마이너한 영화라면, TMDB에서 급히 가져와 끼워넣기
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
            return {"movies": [], "genre": ""} # ✨ 에러 시 반환 형식 맞춤

    # 5. 우리가 만든 AI 추천 로직 실행!
    raw_recommendations = get_recommendations(movie_list, target_movie_id)

    # 6. 추천된 영화 중 중복을 제외하고 데이터 반환
    final_recommendations = []
    for rec in raw_recommendations:
        if rec['id'] not in liked_movie_ids: 
            rec_info = next((m for m in movie_list if m['id'] == rec['id']), None)
            
            if rec_info:
                final_recommendations.append({
                    "id": rec_info.get("id"),
                    "title": rec_info.get("title"),
                    "rating": rec_info.get("vote_average", 0),
                    "poster_url": rec_info.get("poster_url", ""),
                    "overview": rec_info.get("overview", "")
                })

            if len(final_recommendations) >= 10:
                break

    # ✨ 딕셔너리로 장르와 영화 목록 함께 반환
    return {
        "movies": final_recommendations,
        "genre": target_genre
    }