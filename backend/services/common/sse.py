from typing import Final

SSE_DONE: Final[str] = "data: [DONE]\n\n"
SSE_GENERIC_ERROR: Final[str] = "data: [ERROR]Request failed\n\n"


def sse_data(payload: str) -> str:
    escaped = payload.replace("\\", "\\\\").replace("\n", "\\n")
    return f"data: {escaped}\n\n"
