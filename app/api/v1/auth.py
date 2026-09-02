from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from app.api.dependencies import CurrentUser, SessionDep
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import Token, UserLogin
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(user_in: UserCreate, db: SessionDep) -> User:
    """
    Register a new user:
    - Verifies uniqueness of email and username.
    - Hashes password using bcrypt.
    - Persists user to database.
    """
    # Check if a user with the specified email or username already exists
    stmt = select(User).where(
        or_(User.email == user_in.email, User.username == user_in.username)
    )
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.email == user_in.email:
            error_detail = "A user with this email already exists"
        else:
            error_detail = "A user with this username already exists"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and retrieve JWT access token",
)
async def login(credentials: UserLogin, db: SessionDep) -> Token:
    """
    Authenticate a user with email and password:
    - Validates credentials against hashed password.
    - Returns a signed JWT bearer token on success.
    """
    stmt = select(User).where(User.email == credentials.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Encode user ID into JWT subject claim
    access_token = create_access_token(subject=user.id)

    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
async def get_current_user_profile(current_user: CurrentUser) -> User:
    """
    Retrieve profile details for the currently authenticated user.
    """
    return current_user