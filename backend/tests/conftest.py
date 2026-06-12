"""
테스트 공통 설정.
- 실제 MongoDB Atlas 대신 mongomock(인메모리 가짜 DB)로 갈아끼운다.
- 이 교체는 앱(main)을 import 하기 '전에' 이뤄져야 해서 모듈 최상단에서 처리한다.
"""
import os
import sys

# 더미 환경변수 (실제 연결은 하지 않음 — pymongo는 호출 전까진 접속 안 함)
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("TMDB_API_KEY", "test_key")

# backend/ 를 import 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock
import database

# 진짜 컬렉션을 가짜(mongomock)로 교체
_fake_db = mongomock.MongoClient().cinematch_db
database.users_collection = _fake_db.users
database.movies_collection = _fake_db.movies

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def _app():
    # database 패치 이후에 앱을 import (movies.py가 가짜 컬렉션을 잡도록)
    from main import app
    return app


@pytest.fixture
def client(_app):
    return TestClient(_app)


@pytest.fixture(autouse=True)
def reset_state():
    # 매 테스트마다 DB 비우고 추천 캐시 초기화
    database.users_collection.delete_many({})
    database.movies_collection.delete_many({})
    from ai_service.model.recommend import clear_recommendation_cache
    clear_recommendation_cache()
    yield