from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
from dotenv import load_dotenv

# .env 파일에서 숨겨둔 환경변수들을 불러옵니다.
load_dotenv()

# 👉 1. 라우터 임포트 (나중에 안에 코드를 채운 뒤에 주석을 풀 겁니다!)
from routers import users
from routers import movies 

app = FastAPI(title="CineMatch API")

# ✅ CORS 설정 (프론트엔드 연동 대비)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👉 2. 라우터 연결 (이것도 빈 파일이 채워지면 주석을 풉니다!)
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(movies.router, prefix="/api/movies", tags=["Movies"])

# 🔑 TMDB API 키 (.env 파일에서 안전하게 가져오기)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

@app.get("/")
def read_root():
    return {
        "message": "✨ CineMatch 백엔드 서버가 가동 중입니다! ✨",
        "status": "online",
        "docs": "/docs 로 접속하여 API 명세서를 확인하세요."
    }

@app.get("/test-movie")
def test_tmdb():
    """TMDB API 통신 테스트용 엔드포인트"""
    if not TMDB_API_KEY:
        return {"error": "API 키가 설정되지 않았습니다. .env 파일을 확인해주세요."}
        
    url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        response = requests.get(url)
        response.raise_for_status() 
        data = response.json()
        
        # 첫 번째 영화 정보 추출
        first_movie = data['results'][0]
        return {
            "title": first_movie['title'],
            "rating": first_movie['vote_average'],
            "poster_url": f"https://image.tmdb.org/t/p/w500{first_movie['poster_path']}",
            "overview": first_movie['overview']
        }
    except Exception as e:
        return {"error": f"TMDB 연결 실패: {str(e)}"}