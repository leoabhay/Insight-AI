from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from config import settings
from database import get_db

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Helpers
def _create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# Routes
@router.post("/register", status_code=201)
async def register(user: UserCreate):
    db = get_db()
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = pwd_ctx.hash(user.password)
    result = await db.users.insert_one({"email": user.email, "password": hashed, "created_at": datetime.utcnow()})
    return {"user_id": str(result.inserted_id)}

@router.post("/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    user = await db.users.find_one({"email": form.username})
    if not user or not pwd_ctx.verify(form.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_token({"sub": str(user["_id"])})
    return Token(access_token=token)