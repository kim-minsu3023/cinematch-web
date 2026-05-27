from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from database import users_collection  # 우리가 만든 DB 파이프라인 가져오기
from datetime import datetime

# 라우터 생성 (main.py와 연결될 부품)
router = APIRouter()

# 비밀번호 암호화 도구 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 회원가입 시 받을 데이터 형태 정의 (Pydantic 모델)
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: str

# 회원가입 API 엔드포인트
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate):
    # 1. 이미 존재하는 이메일인지 확인
    existing_user = users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")
    
    # 2. 닉네임 중복 확인 (선택 사항이지만 추천!)
    existing_nickname = users_collection.find_one({"nickname": user.nickname})
    if existing_nickname:
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임입니다.")

    # 3. 비밀번호 암호화 (절대 원본 비밀번호를 DB에 저장하면 안 됩니다!)
    hashed_password = pwd_context.hash(user.password)

    # 4. DB에 저장할 사용자 문서(Document) 만들기
    new_user = {
        "email": user.email,
        "password": hashed_password,
        "nickname": user.nickname,
        "created_at": datetime.utcnow()
    }

    # 5. MongoDB에 데이터 쏙 넣기
    result = users_collection.insert_one(new_user)

    # 6. 성공 메시지 반환
    return {
        "message": "회원가입이 완료되었습니다!",
        "user_id": str(result.inserted_id)
    }

# --- 기존 회원가입 코드 아래에 이어서 작성합니다 ---

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
    
    # 2. 비밀번호가 맞는지 확인 (암호화된 비번과 입력한 비번 비교)
    if not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="비밀번호가 틀렸습니다.")
    
    # 3. 이메일도 있고 비밀번호도 맞다면 로그인 성공!
    # (실제 서비스에서는 여기서 '출입증(JWT 토큰)'을 발급하지만, 일단 성공 메시지부터 띄워볼게요!)
    return {
        "message": f"환영합니다, {db_user['nickname']}님!",
        "user_id": str(db_user["_id"])
    }