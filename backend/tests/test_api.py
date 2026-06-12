"""
통합 테스트 — FastAPI 엔드포인트 (TestClient + 가짜 DB)
실제 Atlas/TMDB 없이 API 흐름을 검증한다.
"""
import database
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_user(email="t@t.com", pw="test1234", nickname="테스터",
              genres=None, countries=None, likes=None):
    database.users_collection.insert_one({
        "email": email, "password": pwd.hash(pw), "nickname": nickname,
        "preferred_genres": genres or [], "preferred_countries": countries or [],
        "liked_movies": likes or [],
    })


def seed_movie(mid, title, overview, genre_ids, lang="ko", va=7.0, pop=100.0):
    database.movies_collection.insert_one({
        "id": mid, "title": title, "overview": overview, "genre_ids": genre_ids,
        "original_language": lang, "vote_average": va, "popularity": pop,
        "poster_url": f"http://img/{mid}.jpg", "release_date": "2024-01-01",
    })


# ---------- 기본 ----------
def test_root_alive(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "online"


# ---------- 인증 ----------
def test_register_then_login(client):
    body = {"email": "a@a.com", "password": "pw123456", "nickname": "민수",
            "preferred_genres": [28], "preferred_countries": ["KR"]}
    assert client.post("/api/users/register", json=body).status_code == 200
    r = client.post("/api/users/login", json={"email": "a@a.com", "password": "pw123456"})
    assert r.status_code == 200
    assert "message" in r.json()


def test_login_wrong_password_rejected(client):
    seed_user("b@b.com", "right1234")
    r = client.post("/api/users/login", json={"email": "b@b.com", "password": "wrongpass"})
    assert r.status_code >= 400


def test_profile_returns_nickname(client):
    seed_user("c@c.com", nickname="홍길동", genres=[28, 878])
    r = client.get("/api/users/profile/c@c.com")
    assert r.status_code == 200
    assert r.json()["nickname"] == "홍길동"


# ---------- 찜하기 ----------
def test_like_then_unlike(client):
    seed_user("d@d.com")
    assert client.post("/api/movies/like/100", json={"email": "d@d.com"}).status_code == 200
    assert 100 in client.get("/api/movies/liked-ids/d@d.com").json()
    client.post("/api/movies/unlike/100", json={"email": "d@d.com"})
    assert 100 not in client.get("/api/movies/liked-ids/d@d.com").json()


def test_like_unknown_user_404(client):
    r = client.post("/api/movies/like/1", json={"email": "none@none.com"})
    assert r.status_code == 404


# ---------- 맞춤 추천 ----------
def test_personal_no_likes_empty(client):
    seed_user("e@e.com", likes=[])
    r = client.get("/api/movies/recommendations/personal/e@e.com")
    assert r.status_code == 200
    assert r.json()["movies"] == []


def test_personal_excludes_liked_movie(client):
    seed_movie(1, "한국액션A", "추격 폭발 작전 영웅", [28], lang="ko")
    seed_movie(2, "한국액션B", "총격 전쟁 작전 영웅", [28], lang="ko")
    for i in range(3, 6):
        seed_movie(i, f"외국액션{i}", "추격 폭발 작전 전쟁", [28], lang="en")
    seed_user("f@f.com", likes=[1])
    r = client.get("/api/movies/recommendations/personal/f@f.com")
    assert r.status_code == 200
    movies = r.json()["movies"]
    assert len(movies) > 0
    assert all(m["id"] != 1 for m in movies)  # 찜한 영화는 추천에서 제외


# ---------- 취향 일치도(육각형) ----------
def test_match_returns_six_axes(client):
    seed_movie(10, "영화10", "우주 모험 액션 우주선", [878, 28], lang="ko", va=8.0)
    seed_movie(11, "영화11", "우주 전쟁 우주선", [878], lang="ko", va=7.0)
    seed_user("g@g.com", genres=[878], likes=[11])
    r = client.get("/api/movies/recommendations/match/g@g.com/10")
    assert r.status_code == 200
    scores = r.json()["scores"]
    assert set(scores.keys()) == {"취향 유사도", "장르 적합도", "평점", "인기도", "최신성", "종합 추천도"}
    for v in scores.values():
        assert 0 <= v <= 100


# ---------- AI 자연어 검색 ----------
def test_search_ai_returns_list(client):
    seed_movie(20, "힐링영화", "잔잔한 시골 풍경 따뜻한 가족 이야기", [18, 10751])
    seed_movie(21, "액션영화", "빠른 추격과 폭발 총격전", [28])
    r = client.get("/api/movies/search/ai", params={"query": "잔잔한 가족 이야기"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- TMDB 의존 엔드포인트 (TMDB 호출은 가짜로 대체) ----------
def test_home_sections_with_mocked_tmdb(client, monkeypatch):
    import routers.movies as mv

    class FakeResp:
        status_code = 200
        def json(self):
            return {"results": [
                {"id": 1, "title": "테스트영화", "vote_average": 7.5,
                 "poster_path": "/p.jpg", "overview": "줄거리"}
            ]}
        def raise_for_status(self):
            pass

    monkeypatch.setattr(mv.requests, "get", lambda *a, **k: FakeResp())
    r = client.get("/api/movies/home-sections")
    assert r.status_code == 200
    body = r.json()
    assert "korean" in body and "foreign" in body and "animation" in body