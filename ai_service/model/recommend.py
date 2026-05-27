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

def get_recommendations(movie_list, target_movie_id, top_n=10):
    """
    고도화된 하이브리드 추천 엔진
    (장르 가중치 + 줄거리 유사도 + 대중 평점 혼합형)
    """
    if not movie_list:
        return []

    # 1. MongoDB에서 가져온 영화 리스트를 Pandas 데이터프레임으로 변환
    df = pd.DataFrame(movie_list)

    # 데이터가 비어있을 경우를 대비한 안전 장치(결측치 처리)
    if 'genre_ids' not in df.columns:
        df['genre_ids'] = [[] for _ in range(len(df))]
    if 'overview' not in df.columns:
        df['overview'] = ""
    if 'vote_average' not in df.columns:
        df['vote_average'] = 0.0

    df['overview'] = df['overview'].fillna('')
    df['vote_average'] = df['vote_average'].fillna(0)

    # 2. 장르 ID 배열을 텍스트로 변환하는 함수
    def map_genres(g_ids):
        if isinstance(g_ids, list):
            return " ".join([GENRE_MAP.get(i, "") for i in g_ids])
        return ""

    df['genre_str'] = df['genre_ids'].apply(map_genres)

    # 3. AI 모델이 분석할 핵심 데이터 생성 (장르에 가중치를 주기 위해 장르를 3번 반복 삽입)
    df['combined_features'] = df['genre_str'] + " " + df['genre_str'] + " " + df['genre_str'] + " " + df['overview']

    # 4. TF-IDF 벡터화 (단어의 빈도와 중요도를 수학적 수치로 변환)
    tfidf = TfidfVectorizer()
    tfidf_matrix = tfidf.fit_transform(df['combined_features'])

    # 타겟 영화(유저가 클릭한 영화 또는 찜한 영화)의 인덱스 찾기
    idx_list = df.index[df['id'] == target_movie_id].tolist()
    if not idx_list:
        return [] # 타겟 영화가 없으면 빈 리스트 반환
    target_idx = idx_list[0]

    # 5. 코사인 유사도 계산 (타겟 영화와 나머지 800+개 영화의 유사도 비교)
    sim_scores = cosine_similarity(tfidf_matrix[target_idx], tfidf_matrix).flatten()
    df['similarity'] = sim_scores

    # 6. ✨ 최종 점수(Final Score) 산출 로직
    # 유사도(0~1)를 80%, 평점(0~10점을 0~1로 환산)을 20% 비율로 합산합니다.
    df['norm_rating'] = df['vote_average'] / 10.0
    df['final_score'] = (df['similarity'] * 0.8) + (df['norm_rating'] * 0.2)

    # 7. 최종 점수를 기준으로 내림차순 정렬
    df = df.sort_values(by='final_score', ascending=False)

    # 자기 자신(타겟 영화)은 추천 목록에서 제외
    df = df[df['id'] != target_movie_id]

    # 상위 N개만 추출하여 파이썬 딕셔너리 리스트로 반환
    top_movies = df.head(top_n)
    return top_movies.to_dict('records')