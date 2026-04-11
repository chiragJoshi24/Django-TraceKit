"""
Thread-local request middleware.

Stores the current request so that ``get_time_log()`` and other helpers
can access it from anywhere in the call stack.
"""

from threading import local

_thread_locals = local()


def get_current_request():
    """Return the Django request for the current thread, or None."""
    return getattr(_thread_locals, "request", None)


class RequestMiddleware:
    """
    Must be placed **before** the other tracekit middlewares in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request = None
