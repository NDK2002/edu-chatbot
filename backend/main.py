from fastapi import FastAPI
from backend.routers import chat, solver, teacher

app = FastAPI(title="Edu Chatbot API", version="0.1.0")

app.include_router(chat.router,    prefix="/chat",    tags=["chat"])
app.include_router(solver.router,  prefix="/solver",  tags=["solver"])
app.include_router(teacher.router, prefix="/teacher", tags=["teacher"])

@app.get("/health")
def health():
    return {"status": "ok"}
