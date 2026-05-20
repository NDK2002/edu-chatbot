from fastapi import APIRouter
from pydantic import BaseModel
from sympy import sympify, SympifyError

router = APIRouter()

class SolverRequest(BaseModel):
    expression: str   # vd: "3 * 4", "12 / 3", "15 + 27"

class SolverResponse(BaseModel):
    result: str
    steps: list[str]
    error: str | None = None

@router.post("/", response_model=SolverResponse)
def solve(req: SolverRequest):
    try:
        expr = sympify(req.expression)
        result = str(expr.evalf() if expr.is_number else expr)
        steps = [
            f"Biểu thức: {req.expression}",
            f"Kết quả: {result}",
        ]
        return SolverResponse(result=result, steps=steps)
    except SympifyError as e:
        return SolverResponse(result="", steps=[], error=str(e))
