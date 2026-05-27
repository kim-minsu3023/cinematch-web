import os
from pymongo import MongoClient
from pymongo.collection import Collection  # ✨ 타입 힌트를 위해 Collection 임포트 추가
from dotenv import load_dotenv

# 1. .env 파일에서 환경변수(비밀번호, 주소) 안전하게 불러오기
load_dotenv()
MONGO_URL = os.getenv("MONGODB_URL")

# 2. MongoDB Atlas와 연결하는 클라이언트(배달원) 생성
client = MongoClient(MONGO_URL)
db = client.cinematch_db

# 3. 앞으로 사용할 컬렉션(테이블)에 타입 명시 (VS Code 노란 줄 해결)
users_collection: Collection = db.users
movies_collection: Collection = db.movies

print("✨ MongoDB 파이프라인 세팅 완료!")