import base64
import io

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def fig_to_data_uri(fig: Figure) -> str:
    FigureCanvasAgg(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()
