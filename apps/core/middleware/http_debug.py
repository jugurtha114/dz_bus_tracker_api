"""
Comprehensive HTTP request/response debug logging middleware.
"""
import json
import logging
import re
import time
import uuid

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Paths to skip in debug logging
_SKIP_PATHS = ("/static/", "/media/", "/__debug__/")

# Max body size to log (2KB)
_MAX_BODY_LOG = 2048

# Regex to detect base64 content (data URIs or long base64-like strings)
_BASE64_DATA_URI_RE = re.compile(
    r'(data:[a-zA-Z0-9+/]+;base64,)([A-Za-z0-9+/=\n]{200,})'
)
_BASE64_LONG_RE = re.compile(
    r'(?<![a-zA-Z0-9_])([A-Za-z0-9+/]{200,}={0,2})(?![a-zA-Z0-9_])'
)

_SEPARATOR = "=" * 62
_THIN_SEP = "-" * 62


def _truncate_base64(text):
    """Replace base64 content with truncated placeholders showing original size."""
    def _replace_data_uri(m):
        prefix = m.group(1)
        data = m.group(2)
        size_kb = len(data) * 3 // 4 // 1024
        return f"{prefix}[BASE64 TRUNCATED {size_kb}KB]"

    def _replace_long(m):
        data = m.group(1)
        size_kb = len(data) * 3 // 4 // 1024
        return f"[BASE64 TRUNCATED {size_kb}KB]"

    text = _BASE64_DATA_URI_RE.sub(_replace_data_uri, text)
    text = _BASE64_LONG_RE.sub(_replace_long, text)
    return text


def _mask_auth_header(value):
    """Show only the first 20 chars of auth header values."""
    if len(value) > 20:
        return value[:20] + "***"
    return value


def _format_headers(header_dict, mask_auth=True):
    """Format headers as indented key-value lines."""
    lines = []
    for key, value in sorted(header_dict.items()):
        if mask_auth and key.lower() == "authorization":
            value = _mask_auth_header(value)
        lines.append(f"    {key}: {value}")
    return "\n".join(lines)


def _get_request_headers(request):
    """Extract meaningful HTTP headers from the request META dict."""
    headers = {}
    for key, value in request.META.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value
        elif key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            header_name = key.replace("_", "-").title()
            if value:
                headers[header_name] = value
    return headers


def _get_request_body(request):
    """Get request body, handling JSON and multipart forms."""
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type:
        field_names = list(request.POST.keys())
        file_names = [f"{k} ({v.size} bytes)" for k, v in request.FILES.items()]
        parts = []
        if field_names:
            parts.append(f"Fields: {field_names}")
        if file_names:
            parts.append(f"Files: {file_names}")
        return " | ".join(parts) if parts else "(empty multipart)"

    try:
        body = request.body.decode("utf-8", errors="replace")
    except Exception:
        return "(unreadable body)"

    if not body:
        return None

    # Try to pretty-format JSON
    if "json" in content_type:
        try:
            parsed = json.loads(body)
            body = json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            pass

    body = _truncate_base64(body)
    if len(body) > _MAX_BODY_LOG:
        body = body[:_MAX_BODY_LOG] + f"\n    ... [TRUNCATED, total {len(request.body)} bytes]"
    return body


def _get_response_body(response):
    """Get response body for JSON responses only."""
    content_type = getattr(response, "content_type", "") or ""
    if "application/json" not in content_type:
        return f"({content_type or 'unknown content type'} - not logged)"

    if hasattr(response, "streaming_content"):
        return "(streaming response - not logged)"

    try:
        body = response.content.decode("utf-8", errors="replace")
    except Exception:
        return "(unreadable response body)"

    if not body:
        return None

    try:
        parsed = json.loads(body)
        body = json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        pass

    body = _truncate_base64(body)
    if len(body) > _MAX_BODY_LOG:
        body = body[:_MAX_BODY_LOG] + f"\n    ... [TRUNCATED, total {len(response.content)} bytes]"
    return body


class DebugRequestLogMiddleware(MiddlewareMixin):
    """
    Comprehensive HTTP request/response debug logging middleware.

    When DEBUG=True, logs structured blocks showing:
    - Request method, path, headers, and body
    - Response status, headers, body (JSON only), and timing
    - Base64 content is automatically truncated
    - Auth headers are masked for security
    - Static/media paths are skipped

    No-op when DEBUG=False.
    """

    def process_request(self, request):
        if not settings.DEBUG:
            return

        # Skip static/media/debug paths
        if any(request.path.startswith(p) for p in _SKIP_PATHS):
            return

        request._debug_req_id = uuid.uuid4().hex[:8]
        request._debug_start_time = time.time()

        req_id = request._debug_req_id
        method = request.method
        path = request.get_full_path()
        headers = _get_request_headers(request)
        body = _get_request_body(request)

        lines = [
            "",
            _SEPARATOR,
            f"  REQUEST  [{req_id}] {method} {path}",
            _THIN_SEP,
            "  Headers:",
            _format_headers(headers),
        ]
        if body:
            lines.append("  Body:")
            for line in body.split("\n"):
                lines.append(f"    {line}")
        lines.append(_SEPARATOR)

        logger.debug("\n".join(lines))

    def process_response(self, request, response):
        if not settings.DEBUG:
            return response

        if not hasattr(request, "_debug_req_id"):
            return response

        req_id = request._debug_req_id
        duration_ms = (time.time() - request._debug_start_time) * 1000
        method = request.method
        path = request.get_full_path()
        status = response.status_code
        reason = response.reason_phrase

        resp_headers = {}
        for key, value in response.items():
            resp_headers[key] = value

        body = _get_response_body(response)

        # Status indicator
        indicator = "+" if status < 400 else "!" if status < 500 else "x"

        lines = [
            "",
            _SEPARATOR,
            f"  {indicator} RESPONSE [{req_id}] {status} {reason}  ({duration_ms:.0f}ms)  {method} {path}",
            _THIN_SEP,
            "  Headers:",
            _format_headers(resp_headers, mask_auth=False),
        ]
        if body:
            lines.append("  Body:")
            for line in body.split("\n"):
                lines.append(f"    {line}")
        lines.append(_SEPARATOR)

        logger.debug("\n".join(lines))

        return response
