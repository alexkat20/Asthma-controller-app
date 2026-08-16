"""Рендер фигуры matplotlib в base64 data-URI (для встраивания в JSON-ответ чата)."""

import base64
import io

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def fig_to_data_uri(fig: Figure) -> str:
    """
    Принимает объект Figure явно — НЕ использует глобальное состояние
    matplotlib.pyplot (plt.figure()/plt.savefig()/plt.close()). Это не
    стилистическая деталь: pyplot хранит "текущую фигуру" в глобальной
    переменной процесса, общей для всех потоков. FastAPI выполняет обычные
    (def, не async def) обработчики в пуле потоков — то есть параллельные
    запросы на графики реально исполняются одновременно на разных потоках,
    и все они дерутся за одну и ту же глобальную "текущую фигуру". Под
    нагрузкой это стабильно приводило к 500 Internal Server Error
    (RuntimeError: ... did not call Figure.draw, so no renderer is available) —
    подтверждено нагрузочным тестом (100% отказов на 50 параллельных запросах).

    FigureCanvasAgg(fig) присоединяется явно (а не полагается на то, что
    Figure() сама выберет backend) — так у каждого потока полностью свой,
    ни с кем не разделяемый объект рендеринга от начала до конца.
    """
    FigureCanvasAgg(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()
