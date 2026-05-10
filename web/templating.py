from fastapi.templating import Jinja2Templates
from datetime import date, datetime
from urllib.parse import quote
from stdlib.timezone_util import ensure_app_tz, format_app_datetime

templates = Jinja2Templates(directory="web/templates")

templates.env.filters["datetime"] = lambda v: (
    format_app_datetime(v) if isinstance(v, datetime) else v
)
templates.env.filters["datefmt"] = lambda v: (
    format_app_datetime(v, "%d.%m.%Y")
    if isinstance(v, datetime)
    else (v.strftime("%d.%m.%Y") if isinstance(v, date) else v)
)
templates.env.filters["datetime_local"] = lambda v: (
    ensure_app_tz(v).strftime("%Y-%m-%dT%H:%M") if isinstance(v, datetime) else ""
)
templates.env.filters["urlquote"] = lambda v: quote(str(v or ""), safe="")