"""スキマ日南ファーム＆シー：Webアプリの入口。

起動: uvicorn skima.main:app --reload
"""
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from . import auth
from .config import get_settings
from .db import Base, SessionLocal, engine
from .demo import seed  # noqa: F401（テストからも使う）
from .models import Producer, Student
from .routes_producer import router as producer_router
from .routes_student import router as student_router
from .routes_survey import router as survey_router
from .routes_line import router as line_router
from .routes_teacher import router as teacher_router
from .web import BASE_DIR, render

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    if settings.teacher_passcode == "demo-teacher":
        log.warning("教員パスコードが初期値のままです。EC2では .env の TEACHER_PASSCODE を変更してください。")
    yield


app = FastAPI(title="スキマ日南ファーム＆シー", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or secrets.token_urlsafe(32),
    same_site="lax",  # ほかのサイトからの送信にはログイン情報を付けない
    https_only=settings.base_url.startswith("https://"),
    max_age=60 * 60 * 24 * 14,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(producer_router)
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(survey_router)
app.include_router(line_router)


@app.exception_handler(auth.LoginRequired)
def to_login(request: Request, exc: auth.LoginRequired):
    return RedirectResponse("/login", status_code=303)


HOME = {"producer": "/producer", "student": "/student", "teacher": "/teacher"}


@app.get("/", include_in_schema=False)
def index(request: Request):
    user = auth.current_user(request)
    return RedirectResponse(HOME[user.role] if user else "/login")


@app.get("/login")
def login_page(request: Request, error: str | None = None):
    with SessionLocal() as db:
        producers = list(db.scalars(select(Producer).order_by(Producer.id)))
        students = list(db.scalars(select(Student).order_by(Student.id)))
    return render(request, "login.html", producers=producers, students=students, error=error)


@app.post("/login")
def login_submit(request: Request, role: str = Form(...), user_id: int = Form(0), passcode: str = Form("")):
    with SessionLocal() as db:
        if role == "producer" and (p := db.get(Producer, user_id)):
            auth.login(request, "producer", p.id, p.name)
        elif role == "student" and (s := db.get(Student, user_id)):
            auth.login(request, "student", s.id, s.nickname)
        elif role == "teacher" and secrets.compare_digest(passcode, settings.teacher_passcode):
            auth.login(request, "teacher", 0, "教員")
        else:
            return RedirectResponse("/login?error=1", status_code=303)
    return RedirectResponse(HOME[role], status_code=303)


@app.post("/logout")
def logout(request: Request):
    auth.logout(request)
    return RedirectResponse("/login", status_code=303)


@app.get("/api/health")
def health():
    return {"ok": True}
