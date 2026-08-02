"""Рендер текущей фигуры matplotlib в base64 data-URI (для встраивания в JSON-ответ чата)."""

import base64
import io

import matplotlib

matplotlib.use("Agg")  # без дисплея — рендерим сразу в буфер
import matplotlib.pyplot as plt


def fig_to_data_uri() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close()
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()
