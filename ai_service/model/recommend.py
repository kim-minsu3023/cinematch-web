import threading
from collections import OrderedDict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# TMDB의 장르 ID를 한글 텍스트로 매핑하는 사전
GENRE_MAP = {
    28: "액션", 12: "모험", 16: "애니메이션", 35: "코미디", 80: "범죄",
    99: "다큐멘터리", 18: "드라마", 10751: "가족", 14: "판타지", 36: "역사",
    27: "공포", 10402: "음악", 9648: "미스터리", 10749: "로맨스", 878: "SF",
    10770: "TV영화", 53: "스릴러", 10752: "전쟁", 37: "서부"
}

# -----------------------------------------------------------------
# ✨ TF-IDF 캐시
# 같은 영화 목록이 다시 들어오면 무거운 벡터화(fit_transform)를 건너뛰고
# 이전에 만들어 둔 결과를 재사용한다.
# - 서버가 켜져 있는 동안 메모리에 유지된다.
# - 서버를 재시작하거나 clear_recommendation_cache()를 호출하면 초기화된다.
# - 최근에 사용한 목록 몇 개만 기억하고, 오래된 것은 버린다(LRU).
# -----------------------------------------------------------------
_CACHE_MAXSIZE = 16
_cache = OrderedDict()  # fingerprint -> (df, tfidf_matrix, id_to_idx)
_lock = threading.Lock()


def clear_recommendation_cache():
    """DB를 새로 갱신(수집)한 뒤 호출하면, 다음 요청 때 캐시를 새로 만든다."""
    with _lock:
        _cache.clear()


def _make_fingerprint(movie_list):
    """영화 목록을 식별하는 값. 영화 id 집합이 같으면 같은 목록으로 본다."""
    ids = tuple(sorted(m.get("id") for m in movie_list if m.get("id") is not None))
    return hash(ids)


def _build_index(movie_list):
    """영화 목록 -> (메타데이터 df, TF-IDF 행렬, id->행번호 맵). 여기가 무거운 부분."""
    df = pd.DataFrame(movie_list)

    # 데이터가 비어있을 경우를 대비한 안전 장치(결측치 처리)
    if "genre_ids" not in df.columns:
        df["genre_ids"] = [[] for _ in range(len(df))]
    if "overview" not in df.columns:
        df["overview"] = ""
    if "vote_average" not in df.columns:
        df["vote_average"] = 0.0

    df["overview"] = df["overview"].fillna("")
    df["vote_average"] = df["vote_average"].fillna(0)

    # 장르 ID 배열을 텍스트로 변환
    def map_genres(g_ids):
        if isinstance(g_ids, list):
            return " ".join([GENRE_MAP.get(i, "") for i in g_ids])
        return ""

    df["genre_str"] = df["genre_ids"].apply(map_genres)

    # 장르에 가중치를 주기 위해 장르를 3번 반복 삽입 + 줄거리
    df["combined_features"] = (
        df["genre_str"] + " " + df["genre_str"] + " " + df["genre_str"] + " " + df["overview"]
    )

    # 평점을 0~1로 환산해 미리 계산해 둔다
    df["norm_rating"] = df["vote_average"] / 10.0

    # TF-IDF 벡터화 (가장 비싼 계산)
    tfidf = TfidfVectorizer()
    tfidf_matrix = tfidf.fit_transform(df["combined_features"])

    # 영화 id로 행 번호를 바로 찾기 위한 사전
    id_to_idx = {mid: i for i, mid in enumerate(df["id"].tolist())}

    return df, tfidf_matrix, id_to_idx


def _get_index(movie_list):
    """캐시에 있으면 재사용, 없으면 새로 만들어 캐시에 저장."""
    fingerprint = _make_fingerprint(movie_list)
    with _lock:
        if fingerprint in _cache:
            _cache.move_to_end(fingerprint)   # 방금 사용했다고 표시
            return _cache[fingerprint]

        index = _build_index(movie_list)      # 캐시 미스 → 여기서 한 번만 계산
        _cache[fingerprint] = index
        if len(_cache) > _CACHE_MAXSIZE:
            _cache.popitem(last=False)         # 가장 오래된 항목 제거
        return index


def get_recommendations(movie_list, target_movie_id, top_n=10):
    """
    고도화된 하이브리드 추천 엔진
    (장르 가중치 + 줄거리 유사도 + 대중 평점 혼합형)

    ✨ TF-IDF 벡터화 결과를 캐싱하여, 같은 영화 목록에서는 매번 다시 계산하지 않는다.
    """
    if not movie_list:
        return []

    # 1. 캐시된 인덱스(메타데이터 + TF-IDF 행렬 + id 맵) 가져오기
    df, tfidf_matrix, id_to_idx = _get_index(movie_list)

    # 2. 타겟 영화(유저가 클릭/찜한 영화)의 행 번호 찾기
    target_idx = id_to_idx.get(target_movie_id)
    if target_idx is None:
        return []  # 타겟 영화가 목록에 없으면 빈 리스트 반환

    # 3. 타겟 1개 vs 전체 코사인 유사도 (이 계산은 가볍다)
    sim = cosine_similarity(tfidf_matrix[target_idx], tfidf_matrix).flatten()

    # 4. 최종 점수 = 유사도 80% + 정규화 평점 20%
    norm_rating = df["norm_rating"].values
    final = sim * 0.8 + norm_rating * 0.2

    # 5. 최종 점수 내림차순 정렬 (캐시된 df는 건드리지 않고 별도 배열로 처리)
    order = np.argsort(final)[::-1]

    results = []
    for i in order:
        i = int(i)
        row = df.iloc[i]
        if row["id"] == target_movie_id:
            continue  # 자기 자신은 제외
        rec = row.to_dict()
        rec["similarity"] = float(sim[i])
        rec["final_score"] = float(final[i])
        results.append(rec)
        if len(results) >= top_n:
            break

    return results