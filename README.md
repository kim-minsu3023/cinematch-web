# 🎬 CineMatch (시네매치)
사용자의 취향과 작품의 완성도를 모두 고려한 **하이브리드 AI 영화 추천 웹 서비스**입니다.

## 📌 핵심 기능
* **하이브리드 AI 추천 엔진:** 단순 줄거리 유사도 비교를 넘어, 장르 가중치(TF-IDF)와 대중 평점 데이터를 결합하여 최적의 추천 결과를 제공합니다.
* **자체 대규모 DB 구축:** 외부 API 실시간 의존도를 낮추기 위해 MongoDB에 800+개의 영화 메타데이터를 사전 적재하여 추천 응답 속도를 2초 이내로 최적화했습니다.
* **원스톱 단일 모달 UI:** 페이지 이동 없는 다크 테마 기반의 모달창에서 예고편, 출연진, 관람등급 등을 한 번에 확인할 수 있습니다.
* **안전한 찜하기 로직:** 데이터베이스 레벨(`$addToSet`)에서 찜하기 중복을 완벽하게 차단합니다.

## 🛠 기술 스택
* **Frontend:** Vanilla JS, HTML5, CSS3
* **Backend:** FastAPI (Python)
* **AI & Data:** Pandas, Scikit-learn
* **Database:** MongoDB
* **External API:** TMDB API

## 📂 프로젝트 구조
* `/frontend` : 사용자 UI 및 비동기 API 통신 로직
* `/backend` : FastAPI 기반 메인 비즈니스 로직 및 REST API 서버
* `/ai_service` : Scikit-learn을 활용한 코사인 유사도 및 하이브리드 추천 연산 모듈
* `/crawler-service` : TMDB 초기 데이터 수집 및 MongoDB 배치(Batch) 적재 모듈

## 🚀 실행 방법
1. 저장소 클론 (Clone)
```bash
   git clone [https://github.com/본인아이디/cinematch.git](https://github.com/본인아이디/cinematch.git)
