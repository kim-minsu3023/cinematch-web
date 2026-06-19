# 🎬 CineMatch (시네매치)

사용자의 취향과 작품의 완성도를 모두 고려한 **하이브리드 AI 영화 추천 웹 서비스**입니다.

CineMatch는 영화를 직접 재생하는 스트리밍 서비스가 아니라, 영화 정보를 제공하고 취향에 맞는 작품을 추천하는 **정보·추천 서비스**입니다. (넷플릭스·티빙 같은 콘텐츠 제공 플랫폼이 아니라, 왓챠피디아·키노라이츠처럼 "무엇을 볼지" 결정하도록 돕는 데 초점을 둡니다.)

## 🔗 바로 사용해보기 (배포 링크)

별도 설치 없이 아래 주소로 접속하면 바로 사용할 수 있습니다.

- **서비스(웹):** https://cinematch-web-one.vercel.app
- **백엔드 API 문서:** https://cinematch-web-3cut.onrender.com/docs

> ⚠️ 백엔드는 무료 인스턴스(Render)로 운영되어, 일정 시간 미사용 시 절전 상태가 됩니다. 첫 접속 시 서버가 깨어나는 데 약 1분이 걸릴 수 있습니다.

## 📌 핵심 기능

- **하이브리드 AI 추천 엔진:** 단순 줄거리 유사도 비교를 넘어, 장르 가중치(TF-IDF)와 대중 평점 데이터를 결합하여 최적의 추천 결과를 제공합니다.
- **자체 대규모 DB 구축:** 외부 API 실시간 의존도를 낮추기 위해 MongoDB에 800+개의 영화 메타데이터를 사전 적재하여 추천 응답 속도를 최적화했습니다.
- **취향 육각형 시각화:** 추천 영화가 내 취향에 얼마나 맞는지를 취향 유사도·장르·평점·인기도·최신성·종합 6개 축의 레이더 차트로 시각화합니다.
- **AI 자연어 검색:** 검색창에 `/`를 붙이면 제목이 아닌 줄거리의 의미적 유사도로 검색합니다. (예: `/감동적인 가족 영화`)
- **원스톱 단일 모달 UI:** 페이지 이동 없는 다크 테마 기반의 모달창에서 예고편, 출연진, 관람등급, 보러가기(OTT·극장)를 한 번에 확인할 수 있습니다.
- **안전한 찜하기 로직:** 데이터베이스 레벨(`$addToSet`)에서 찜하기 중복을 완벽하게 차단합니다.

## 🛠 기술 스택

- **Frontend:** Vanilla JS, HTML5, CSS3
- **Backend:** FastAPI (Python)
- **AI & Data:** Pandas, Scikit-learn
- **Database:** MongoDB (Atlas)
- **External API:** TMDB API
- **배포:** Vercel(프론트엔드), Render(백엔드)

## 📂 프로젝트 구조

- `/frontend` : 사용자 UI 및 비동기 API 통신 로직
- `/backend` : FastAPI 기반 메인 비즈니스 로직 및 REST API 서버
- `/ai_service` : Scikit-learn을 활용한 코사인 유사도 및 하이브리드 추천 연산 모듈
- `/crawler-service` : TMDB 초기 데이터 수집 및 MongoDB 배치(Batch) 적재 모듈

## 🚀 로컬에서 실행하는 방법

> 배포된 사이트로 접속하면 바로 사용할 수 있으며, 아래는 코드를 직접 내려받아 실행하려는 경우의 안내입니다.

### 1. 저장소 클론 (Clone)

```bash
git clone https://github.com/kim-minsu3023/cinematch-web.git
cd cinematch-web
```

### 2. 환경 변수(.env) 설정

보안을 위해 API 키와 DB 주소는 저장소에 포함되어 있지 않습니다. `backend/` 폴더에 `.env` 파일을 만들고 아래 값을 채워주세요.

```env
TMDB_API_KEY=발급받은_TMDB_API_키
MONGODB_URL=본인의_MongoDB_연결_주소
FRONTEND_URL=http://127.0.0.1:5500
```

- **TMDB API 키:** https://www.themoviedb.org 가입 후 [설정 → API]에서 무료 발급
- **MongoDB 주소:** MongoDB Atlas에서 클러스터 생성 후 연결 문자열(Connection String) 복사

### 3. 백엔드 실행

```bash
cd backend
python -m venv cinematch_env           # 가상환경 생성
source cinematch_env/bin/activate      # (Windows: cinematch_env\Scripts\activate)
pip install -r requirements.txt        # 라이브러리 설치
uvicorn main:app --reload              # 서버 실행 (http://127.0.0.1:8000)
```

서버가 켜지면 `http://127.0.0.1:8000/docs` 에서 API 문서를 확인할 수 있습니다.

### 4. (최초 1회) 영화 데이터 수집

DB가 비어 있다면, TMDB에서 영화 데이터를 수집해 MongoDB에 적재합니다.

```bash
python ../crawler-service/collect_movies.py
```

### 5. 프론트엔드 실행

`frontend/index.html`을 브라우저로 열거나, VS Code의 Live Server 등으로 실행합니다.

> 로컬에서 실행할 경우, 프론트엔드 코드가 호출하는 백엔드 주소를 로컬 주소(`http://127.0.0.1:8000`)로 맞춰야 합니다. (배포본은 Render 주소를 호출하도록 설정되어 있습니다.)

## 🧪 테스트

```bash
cd backend
source cinematch_env/bin/activate
python -m pytest tests/ -v --cov=. --cov=../ai_service
```

- 유닛·통합 테스트 19개, 코드 커버리지 73%

## 👥 팀 정보

- 팀명: 소프트웨어 공학 9조
- 팀원: 김민수, 박준희, 진민성