"""
유닛 테스트 — 추천 엔진(ai_service/model/recommend.py)
외부 연결(DB·TMDB) 없이 순수 로직만 검증한다.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # ai_service 경로

from ai_service.model.recommend import (
    get_recommendations, clear_recommendation_cache, GENRE_MAP,
)


def sample_movies():
    return [
        {"id": 1, "title": "A", "overview": "우주 탐험 모험 우주선", "vote_average": 8.0, "genre_ids": [878, 12]},
        {"id": 2, "title": "B", "overview": "우주 전쟁 액션 우주선", "vote_average": 7.0, "genre_ids": [878, 28]},
        {"id": 3, "title": "C", "overview": "로맨스 사랑 이별 이야기", "vote_average": 6.0, "genre_ids": [10749]},
        {"id": 4, "title": "D", "overview": "가족 코미디 즐거운 하루", "vote_average": 5.0, "genre_ids": [35, 10751]},
    ]


def test_empty_list_returns_empty():
    assert get_recommendations([], 1) == []


def test_target_not_in_list_returns_empty():
    assert get_recommendations(sample_movies(), 99999) == []


def test_excludes_self():
    recs = get_recommendations(sample_movies(), 1, top_n=10)
    assert all(r["id"] != 1 for r in recs)


def test_respects_top_n():
    recs = get_recommendations(sample_movies(), 1, top_n=2)
    assert len(recs) <= 2


def test_scores_in_valid_range():
    recs = get_recommendations(sample_movies(), 1, top_n=10)
    for r in recs:
        assert 0.0 <= r["similarity"] <= 1.0001
        assert 0.0 <= r["final_score"] <= 1.0001


def test_similar_genre_ranks_higher():
    # 1번(SF·우주)에는 2번(SF·우주)이 3번(로맨스)보다 더 비슷해야 한다
    recs = get_recommendations(sample_movies(), 1, top_n=10)
    sim = {r["id"]: r["similarity"] for r in recs}
    assert sim[2] > sim[3]


def test_cache_gives_consistent_results():
    clear_recommendation_cache()
    movies = sample_movies()
    first = get_recommendations(movies, 1, top_n=10)
    second = get_recommendations(movies, 1, top_n=10)  # 두 번째는 캐시 사용
    assert [r["id"] for r in first] == [r["id"] for r in second]


def test_genre_map_has_core_genres():
    assert GENRE_MAP[28] == "액션"
    assert GENRE_MAP[878] == "SF"