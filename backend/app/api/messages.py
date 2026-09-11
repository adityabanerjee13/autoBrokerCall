"""Message routes.

The handler lives in outbound/send.py so that the one sending code path in the
system sits next to the providers it drives, not in the API layer.
"""
from app.outbound.send import router  # noqa: F401  (re-exported for main.py)
