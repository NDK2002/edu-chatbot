"""
Rule Engine cho Toán tiểu học lớp 1–5.
Nhận formula_key + params, trả về MathResult có steps giải chi tiết.
Không để LLM tính số — mọi phép tính đều qua đây.
"""

import ast
from dataclasses import dataclass, field
from fractions import Fraction
import math


@dataclass
class MathResult:
    formula_key: str
    answer: str                     # kết quả dạng chuỗi (có đơn vị nếu cần)
    steps: list[str]                # các bước giải
    formula: str = ""               # công thức tổng quát
    error: str = ""                 # nếu có lỗi (thiếu tham số, chia 0, ...)

    @property
    def ok(self) -> bool:
        return not self.error


# ---------------------------------------------------------------------------
# Phép tính cơ bản
# ---------------------------------------------------------------------------

def addition(a: float, b: float, unit: str = "") -> MathResult:
    result = a + b
    u = f" {unit}" if unit else ""
    return MathResult(
        formula_key="addition",
        formula="Tổng = số hạng + số hạng",
        answer=f"{_fmt(result)}{u}",
        steps=[
            f"{_fmt(a)}{u} + {_fmt(b)}{u} = {_fmt(result)}{u}",
        ],
    )


def subtraction(a: float, b: float, unit: str = "") -> MathResult:
    result = a - b
    u = f" {unit}" if unit else ""
    return MathResult(
        formula_key="subtraction",
        formula="Hiệu = số bị trừ − số trừ",
        answer=f"{_fmt(result)}{u}",
        steps=[
            f"{_fmt(a)}{u} − {_fmt(b)}{u} = {_fmt(result)}{u}",
        ],
    )


def multiplication(a: float, b: float, unit: str = "") -> MathResult:
    result = a * b
    u = f" {unit}" if unit else ""
    return MathResult(
        formula_key="multiplication",
        formula="Tích = thừa số × thừa số",
        answer=f"{_fmt(result)}{u}",
        steps=[
            f"{_fmt(a)} × {_fmt(b)} = {_fmt(result)}{u}",
        ],
    )


def division(a: float, b: float, unit: str = "") -> MathResult:
    if b == 0:
        return MathResult(formula_key="division", answer="", steps=[], error="Không thể chia cho 0.")
    result = a / b
    u = f" {unit}" if unit else ""
    return MathResult(
        formula_key="division",
        formula="Thương = số bị chia ÷ số chia",
        answer=f"{_fmt(result)}{u}",
        steps=[
            f"{_fmt(a)} ÷ {_fmt(b)} = {_fmt(result)}{u}",
        ],
    )


# ---------------------------------------------------------------------------
# Bảng nhân / bảng chia
# ---------------------------------------------------------------------------

def multiplication_table(n: int) -> MathResult:
    if n < 2 or n > 9:
        return MathResult(formula_key="multiplication_table", answer="", steps=[],
                            error=f"Bảng nhân {n} không có trong chương trình lớp 1–5.")
    rows = [f"{n} × {i} = {n * i}" for i in range(1, 11)]
    return MathResult(
        formula_key="multiplication_table",
        formula=f"Bảng nhân {n}",
        answer=f"Bảng nhân {n} có 10 phép tính.",
        steps=rows,
    )


def division_table(n: int) -> MathResult:
    if n < 2 or n > 9:
        return MathResult(formula_key="division_table", answer="", steps=[],
                            error=f"Bảng chia {n} không có trong chương trình lớp 1–5.")
    rows = [f"{n * i} ÷ {n} = {i}" for i in range(1, 11)]
    return MathResult(
        formula_key="division_table",
        formula=f"Bảng chia {n}",
        answer=f"Bảng chia {n} có 10 phép tính.",
        steps=rows,
    )


# ---------------------------------------------------------------------------
# Hình học phẳng — chu vi
# ---------------------------------------------------------------------------

def rectangle_perimeter(length: float, width: float, unit: str = "cm") -> MathResult:
    result = (length + width) * 2
    return MathResult(
        formula_key="rectangle_perimeter",
        formula="Chu vi hình chữ nhật = (chiều dài + chiều rộng) × 2",
        answer=f"{_fmt(result)} {unit}",
        steps=[
            "Áp dụng công thức: P = (dài + rộng) × 2",
            f"P = ({_fmt(length)} + {_fmt(width)}) × 2",
            f"P = {_fmt(length + width)} × 2",
            f"P = {_fmt(result)} {unit}",
        ],
    )


def square_perimeter(side: float, unit: str = "cm") -> MathResult:
    result = side * 4
    return MathResult(
        formula_key="square_perimeter",
        formula="Chu vi hình vuông = cạnh × 4",
        answer=f"{_fmt(result)} {unit}",
        steps=[
            "Áp dụng công thức: P = cạnh × 4",
            f"P = {_fmt(side)} × 4",
            f"P = {_fmt(result)} {unit}",
        ],
    )


def triangle_perimeter(a: float, b: float, c: float, unit: str = "cm") -> MathResult:
    result = a + b + c
    return MathResult(
        formula_key="triangle_perimeter",
        formula="Chu vi hình tam giác = cạnh a + cạnh b + cạnh c",
        answer=f"{_fmt(result)} {unit}",
        steps=[
            f"P = {_fmt(a)} + {_fmt(b)} + {_fmt(c)}",
            f"P = {_fmt(result)} {unit}",
        ],
    )


# ---------------------------------------------------------------------------
# Hình học phẳng — diện tích
# ---------------------------------------------------------------------------

def rectangle_area(length: float, width: float, unit: str = "cm") -> MathResult:
    result = length * width
    u2 = f"{unit}²"
    return MathResult(
        formula_key="rectangle_area",
        formula="Diện tích hình chữ nhật = chiều dài × chiều rộng",
        answer=f"{_fmt(result)} {u2}",
        steps=[
            "Áp dụng công thức: S = dài × rộng",
            f"S = {_fmt(length)} × {_fmt(width)}",
            f"S = {_fmt(result)} {u2}",
        ],
    )


def square_area(side: float, unit: str = "cm") -> MathResult:
    result = side * side
    u2 = f"{unit}²"
    return MathResult(
        formula_key="square_area",
        formula="Diện tích hình vuông = cạnh × cạnh",
        answer=f"{_fmt(result)} {u2}",
        steps=[
            f"S = {_fmt(side)} × {_fmt(side)}",
            f"S = {_fmt(result)} {u2}",
        ],
    )


def triangle_area(base: float, height: float, unit: str = "cm") -> MathResult:
    result = base * height / 2
    u2 = f"{unit}²"
    return MathResult(
        formula_key="triangle_area",
        formula="Diện tích hình tam giác = đáy × chiều cao ÷ 2",
        answer=f"{_fmt(result)} {u2}",
        steps=[
            "S = đáy × chiều cao ÷ 2",
            f"S = {_fmt(base)} × {_fmt(height)} ÷ 2",
            f"S = {_fmt(base * height)} ÷ 2",
            f"S = {_fmt(result)} {u2}",
        ],
    )


def trapezoid_area(a: float, b: float, height: float, unit: str = "cm") -> MathResult:
    result = (a + b) * height / 2
    u2 = f"{unit}²"
    return MathResult(
        formula_key="trapezoid_area",
        formula="Diện tích hình thang = (đáy lớn + đáy bé) × chiều cao ÷ 2",
        answer=f"{_fmt(result)} {u2}",
        steps=[
            "S = (đáy lớn + đáy bé) × chiều cao ÷ 2",
            f"S = ({_fmt(a)} + {_fmt(b)}) × {_fmt(height)} ÷ 2",
            f"S = {_fmt(a + b)} × {_fmt(height)} ÷ 2",
            f"S = {_fmt((a + b) * height)} ÷ 2",
            f"S = {_fmt(result)} {u2}",
        ],
    )


# ---------------------------------------------------------------------------
# Hình tròn
# ---------------------------------------------------------------------------

def circle_circumference(radius: float, unit: str = "cm") -> MathResult:
    result = 2 * math.pi * radius
    return MathResult(
        formula_key="circle_circumference",
        formula="Chu vi hình tròn = 2 × 3,14 × bán kính",
        answer=f"{round(result, 2)} {unit}",
        steps=[
            "C = 2 × 3,14 × r",
            f"C = 2 × 3,14 × {_fmt(radius)}",
            f"C = {round(result, 2)} {unit}",
        ],
    )


def circle_area(radius: float, unit: str = "cm") -> MathResult:
    result = math.pi * radius * radius
    u2 = f"{unit}²"
    return MathResult(
        formula_key="circle_area",
        formula="Diện tích hình tròn = 3,14 × bán kính × bán kính",
        answer=f"{round(result, 2)} {u2}",
        steps=[
            "S = 3,14 × r × r",
            f"S = 3,14 × {_fmt(radius)} × {_fmt(radius)}",
            f"S = {round(result, 2)} {u2}",
        ],
    )


# ---------------------------------------------------------------------------
# Hình khối — thể tích
# ---------------------------------------------------------------------------

def box_volume(length: float, width: float, height: float, unit: str = "cm") -> MathResult:
    result = length * width * height
    u3 = f"{unit}³"
    return MathResult(
        formula_key="box_volume",
        formula="Thể tích hình hộp chữ nhật = dài × rộng × cao",
        answer=f"{_fmt(result)} {u3}",
        steps=[
            "V = dài × rộng × cao",
            f"V = {_fmt(length)} × {_fmt(width)} × {_fmt(height)}",
            f"V = {_fmt(result)} {u3}",
        ],
    )


def cube_volume(side: float, unit: str = "cm") -> MathResult:
    result = side ** 3
    u3 = f"{unit}³"
    return MathResult(
        formula_key="cube_volume",
        formula="Thể tích hình lập phương = cạnh × cạnh × cạnh",
        answer=f"{_fmt(result)} {u3}",
        steps=[
            "V = cạnh × cạnh × cạnh",
            f"V = {_fmt(side)} × {_fmt(side)} × {_fmt(side)}",
            f"V = {_fmt(result)} {u3}",
        ],
    )


# ---------------------------------------------------------------------------
# Tốc độ — quãng đường — thời gian
# ---------------------------------------------------------------------------

def speed_from_distance_time(distance: float, time: float,
                                d_unit: str = "km", t_unit: str = "giờ") -> MathResult:
    if time == 0:
        return MathResult(formula_key="speed_distance_time", answer="", steps=[],
                        error="Thời gian không thể bằng 0.")
    result = distance / time
    return MathResult(
        formula_key="speed_distance_time",
        formula="Vận tốc = quãng đường ÷ thời gian",
        answer=f"{_fmt(result)} {d_unit}/{t_unit}",
        steps=[
            "v = s ÷ t",
            f"v = {_fmt(distance)} ÷ {_fmt(time)}",
            f"v = {_fmt(result)} {d_unit}/{t_unit}",
        ],
    )


def distance_from_speed_time(speed: float, time: float,
                                s_unit: str = "km", t_unit: str = "giờ") -> MathResult:
    result = speed * time
    return MathResult(
        formula_key="speed_distance_time",
        formula="Quãng đường = vận tốc × thời gian",
        answer=f"{_fmt(result)} {s_unit}",
        steps=[
            "s = v × t",
            f"s = {_fmt(speed)} × {_fmt(time)}",
            f"s = {_fmt(result)} {s_unit}",
        ],
    )


def time_from_distance_speed(distance: float, speed: float,
                                d_unit: str = "km", t_unit: str = "giờ") -> MathResult:
    if speed == 0:
        return MathResult(formula_key="speed_distance_time", answer="", steps=[],
                            error="Vận tốc không thể bằng 0.")
    result = distance / speed
    return MathResult(
        formula_key="speed_distance_time",
        formula="Thời gian = quãng đường ÷ vận tốc",
        answer=f"{_fmt(result)} {t_unit}",
        steps=[
            "t = s ÷ v",
            f"t = {_fmt(distance)} ÷ {_fmt(speed)}",
            f"t = {_fmt(result)} {t_unit}",
        ],
    )


# ---------------------------------------------------------------------------
# Tỉ số phần trăm
# ---------------------------------------------------------------------------

def percent_of_number(number: float, percent: float) -> MathResult:
    result = number * percent / 100
    return MathResult(
        formula_key="percent",
        formula="Giá trị = số × tỉ số phần trăm ÷ 100",
        answer=_fmt(result),
        steps=[
            f"{_fmt(percent)}% của {_fmt(number)}",
            f"= {_fmt(number)} × {_fmt(percent)} ÷ 100",
            f"= {_fmt(result)}",
        ],
    )


def find_percent_rate(part: float, whole: float) -> MathResult:
    if whole == 0:
        return MathResult(formula_key="percent", answer="", steps=[],
                            error="Số gốc không thể bằng 0.")
    result = part / whole * 100
    return MathResult(
        formula_key="percent",
        formula="Tỉ số phần trăm = phần ÷ tổng × 100%",
        answer=f"{round(result, 2)}%",
        steps=[
            f"Tỉ số phần trăm = {_fmt(part)} ÷ {_fmt(whole)} × 100%",
            f"= {round(result, 2)}%",
        ],
    )


def find_original_from_percent(part: float, percent: float) -> MathResult:
    if percent == 0:
        return MathResult(formula_key="percent", answer="", steps=[],
                            error="Tỉ số phần trăm không thể bằng 0.")
    result = part / percent * 100
    return MathResult(
        formula_key="percent",
        formula="Số gốc = giá trị ÷ tỉ số phần trăm × 100",
        answer=_fmt(result),
        steps=[
            f"Số gốc = {_fmt(part)} ÷ {_fmt(percent)}% × 100",
            f"= {_fmt(part)} ÷ {_fmt(percent)} × 100",
            f"= {_fmt(result)}",
        ],
    )


# ---------------------------------------------------------------------------
# Đổi đơn vị
# ---------------------------------------------------------------------------

_LENGTH_TO_MM: dict[str, float] = {
    "mm": 1, "cm": 10, "dm": 100, "m": 1000, "km": 1_000_000,
}
_MASS_TO_MG: dict[str, float] = {
    "mg": 1, "g": 1000, "kg": 1_000_000, "tấn": 1_000_000_000,
}
_AREA_TO_CM2: dict[str, float] = {
    "mm²": 0.01, "cm²": 1, "dm²": 100, "m²": 10_000,
    "km²": 10_000_000_000, "ha": 100_000_000, "a": 1_000_000,
}
_TIME_TO_SEC: dict[str, float] = {
    "giây": 1, "phút": 60, "giờ": 3600, "ngày": 86400,
}


def _unit_convert(value: float, from_unit: str, to_unit: str,
                    table: dict[str, float], formula_key: str) -> MathResult:
    fu = from_unit.lower()
    tu = to_unit.lower()
    if fu not in table:
        return MathResult(formula_key=formula_key, answer="", steps=[],
                            error=f"Đơn vị '{from_unit}' không hợp lệ.")
    if tu not in table:
        return MathResult(formula_key=formula_key, answer="", steps=[],
                            error=f"Đơn vị '{to_unit}' không hợp lệ.")
    result = value * table[fu] / table[tu]
    return MathResult(
        formula_key=formula_key,
        formula=f"Đổi {from_unit} sang {to_unit}",
        answer=f"{_fmt(result)} {to_unit}",
        steps=[
            f"{_fmt(value)} {from_unit} = {_fmt(result)} {to_unit}",
        ],
    )


def length_conversion(value: float, from_unit: str, to_unit: str) -> MathResult:
    return _unit_convert(value, from_unit, to_unit, _LENGTH_TO_MM, "unit_conversion")


def mass_conversion(value: float, from_unit: str, to_unit: str) -> MathResult:
    return _unit_convert(value, from_unit, to_unit, _MASS_TO_MG, "unit_conversion")


def area_conversion(value: float, from_unit: str, to_unit: str) -> MathResult:
    return _unit_convert(value, from_unit, to_unit, _AREA_TO_CM2, "unit_conversion")


def time_conversion(value: float, from_unit: str, to_unit: str) -> MathResult:
    return _unit_convert(value, from_unit, to_unit, _TIME_TO_SEC, "unit_conversion")


# ---------------------------------------------------------------------------
# Biểu thức số học tổng quát (có dấu ngoặc, nhiều toán tử)
# ---------------------------------------------------------------------------

def _expr_steps(node: ast.expr) -> list[str]:
    """Sinh bước tính trung gian từ AST — chỉ thêm bước khi có biểu thức con."""
    _VI = {ast.Add: "+", ast.Sub: "−", ast.Mult: "×", ast.Div: "÷"}

    def _eval(n: ast.expr) -> tuple[float, list[str]]:
        if isinstance(n, ast.Constant):
            return float(n.value), []
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            v, s = _eval(n.operand)
            return -v, s
        if isinstance(n, ast.BinOp):
            lv, ls = _eval(n.left)
            rv, rs = _eval(n.right)
            vi_op = _VI.get(type(n.op), "?")
            if isinstance(n.op, ast.Add):
                res = lv + rv
            elif isinstance(n.op, ast.Sub):
                res = lv - rv
            elif isinstance(n.op, ast.Mult):
                res = lv * rv
            else:
                res = lv / rv if rv else 0.0
            combined = ls + rs
            if not isinstance(n.left, ast.Constant) or not isinstance(n.right, ast.Constant):
                combined.append(f"{_fmt(lv)} {vi_op} {_fmt(rv)} = {_fmt(res)}")
            return res, combined
        return 0.0, []

    _, steps = _eval(node)
    return steps


def arithmetic_expression(expr: str) -> MathResult:
    """Tính biểu thức số học tổng quát (đã xác nhận an toàn bởi intent_detector)."""
    display = expr.replace("*", "×").replace("/", "÷")
    try:
        allowed = {ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub}
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if type(node) not in allowed:
                return MathResult(formula_key="arithmetic_expression", answer="", steps=[],
                                    error="Biểu thức không hợp lệ.")
        result = eval(compile(expr, "<string>", "eval"))  # noqa: S307 — AST đã kiểm tra
        intermediate = _expr_steps(tree.body)
        if intermediate:
            steps = [f"Biểu thức: {display}"] + intermediate + [f"Kết quả: {_fmt(result)}"]
        else:
            steps = [f"{display} = {_fmt(result)}"]
        return MathResult(
            formula_key="arithmetic_expression",
            formula=display,
            answer=_fmt(result),
            steps=steps,
        )
    except ZeroDivisionError:
        return MathResult(formula_key="arithmetic_expression", answer="", steps=[],
                            error="Không thể chia cho 0.")
    except Exception as exc:
        return MathResult(formula_key="arithmetic_expression", answer="", steps=[], error=str(exc))


# ---------------------------------------------------------------------------
# Dispatch table — ánh xạ formula_key → hàm (dùng cho intent detector)
# ---------------------------------------------------------------------------

RULES: dict[str, object] = {
    "addition": addition,
    "subtraction": subtraction,
    "multiplication": multiplication,
    "division": division,
    "multiplication_table": multiplication_table,
    "division_table": division_table,
    "rectangle_perimeter": rectangle_perimeter,
    "square_perimeter": square_perimeter,
    "triangle_perimeter": triangle_perimeter,
    "rectangle_area": rectangle_area,
    "square_area": square_area,
    "triangle_area": triangle_area,
    "trapezoid_area": trapezoid_area,
    "circle_circumference": circle_circumference,
    "circle_area": circle_area,
    "box_volume": box_volume,
    "cube_volume": cube_volume,
    "speed_from_distance_time": speed_from_distance_time,
    "distance_from_speed_time": distance_from_speed_time,
    "time_from_distance_speed": time_from_distance_speed,
    "percent_of_number": percent_of_number,
    "find_percent_rate": find_percent_rate,
    "find_original_from_percent": find_original_from_percent,
    "length_conversion": length_conversion,
    "mass_conversion": mass_conversion,
    "area_conversion": area_conversion,
    "time_conversion": time_conversion,
    "arithmetic_expression": arithmetic_expression,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(n: float) -> str:
    """Hiển thị số: bỏ .0 nếu là số nguyên, dùng dấu phẩy thập phân."""
    if isinstance(n, int) or (isinstance(n, float) and n == int(n)):
        return str(int(n))
    return f"{n:g}".replace(".", ",")
