import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import chat, chat_v2, solver, teacher
from backend.middleware.rate_limit_middleware import RateLimitMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Edu Chatbot API", version="0.1.0", redirect_slashes=False)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router,    prefix="/chat",    tags=["chat"])
app.include_router(chat_v2.router, prefix="/v2/chat", tags=["chat_v2"])
app.include_router(solver.router,  prefix="/solver",  tags=["solver"])
app.include_router(teacher.router, prefix="/teacher", tags=["teacher"])

@app.get("/health")
def health():
    return {"status": "ok"}
