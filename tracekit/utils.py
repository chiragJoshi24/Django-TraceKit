import re
import uuid

from tracekit.settings import get_setting


def normalize_url(path: str) -> str:
    return re.sub(r"/\d+(?=/|$)", "/id", path)


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        parts = x_forwarded_for.split(",")
        # Second entry is the real client IP behind a load balancer;
        # fall back to first if only one entry.
        ip = parts[1].strip() if len(parts) > 1 else parts[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip


def get_request_id(request) -> str:
    attr = "_tracekit_request_id"
    if hasattr(request, attr):
        return getattr(request, attr)

    header = get_setting("REQUEST_ID_HEADER")
    request_id = request.META.get(header, "")
    if not request_id:
        request_id = str(uuid.uuid4())
    setattr(request, attr, request_id)
    return request_id


def split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
