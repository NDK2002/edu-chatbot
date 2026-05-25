import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import chat, solver, teacher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Edu Chatbot API", version="0.1.0", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router,    prefix="/chat",    tags=["chat"])
app.include_router(solver.router,  prefix="/solver",  tags=["solver"])
app.include_router(teacher.router, prefix="/teacher", tags=["teacher"])

@app.get("/health")
def health():
    return {"status": "ok"}
