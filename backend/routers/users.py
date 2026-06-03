from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from database import users_collection 
from datetime import datetime
from typing import List, Optional # ✨ 리스트와 선택적 데이터를 받기 위해 추가

# 라우터 생성
router = APIRouter()

# 비밀번호 암호화 도구 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ✨ 회원가입 시 받을 데이터 형태 정의 (취향 정보 추가)
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: str
    preferred_genres: Optional[List[int]] = []     # 예: [28, 12, 16] (액션, 모험, 애니메이션)
    preferred_countries: Optional[List[str]] = []  # 예: ["KR", "US"]

# 회원가입 API 엔드포인트
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate):
    # 1. 이미 존재하는 이메일인지 확인
    existing_user = users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")
    
    # 2. 닉네임 중복 확인
    existing_nickname = users_collection.find_one({"nickname": user.nickname})
    if existing_nickname:
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임입니다.")

    # 3. 비밀번호 암호화 
    hashed_password = pwd_context.hash(user.password)

    # 4. ✨ DB에 저장할 사용자 문서(Document) 만들기 (취향 및 찜목록 초기화 추가)
    new_user = {
        "email": user.email,
        "password": hashed_password,
        "nickname": user.nickname,
        "preferred_genres": user.preferred_genres,       # 선호 장르 저장
        "preferred_countries": user.preferred_countries, # 선호 국가 저장
        "liked_movies": [],                              # 찜 목록 초기화 (에러 방지용)
        "created_at": datetime.utcnow()
    }

    # 5. MongoDB에 데이터 쏙 넣기
    result = users_collection.insert_one(new_user)

    # 6. 성공 메시지 반환
    return {
        "message": "회원가입이 완료되었습니다!",
        "user_id": str(result.inserted_id)
    }

# 로그인 시 받을 데이터 형태 정의
class UserLogin(BaseModel):
    email: str
    password: str

# 로그인 API 엔드포인트
@router.post("/login")
def login_user(user: UserLogin):
    # 1. DB에서 이메일 찾기
    db_user = users_collection.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(status_code=400, detail="가입되지 않은 이메일입니다.")
    
    # 2. 비밀번호가 맞는지 확인 
    if not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="비밀번호가 틀렸습니다.")
    
    # 3. 성공 메시지 반환
    return {
        "message": f"환영합니다, {db_user['nickname']}님!",
        "user_id": str(db_user["_id"])
    }

# -------------------------------------------------------------
# ✨ [추가됨] 유저 프로필(닉네임 등) 조회 API
# -------------------------------------------------------------
@router.get("/profile/{email}")
def get_user_profile(email: str):
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    
    return {
        "email": user["email"],
        "nickname": user.get("nickname", "회원"),
        "preferred_genres": user.get("preferred_genres", []),
        "preferred_countries": user.get("preferred_countries", [])
    }