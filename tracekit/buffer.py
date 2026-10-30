"""
In-memory write buffers, flushed to the database by a background thread.

Started on process start by TracekitConfig.ready(). Usage:

    from tracekit.buffer import BufferManager

    BufferManager().get("api_log").add(APILog(...))

Register your own buffers once, e.g. in your AppConfig.ready():

    events = BufferManager().register("events", Event)
    events.add(Event(...))

Buffers can only be created through register(); a Buffer the manager
doesn't know about would never be flushed.
"""

import atexit
import logging
import os
import threading

from django.db import DataError, IntegrityError, close_old_connections
from django.db.models import Model
from tracekit.models import APILog
from tracekit.settings import get_setting

logger = logging.getLogger("tracekit")

_REGISTER_KEY = object()


class Buffer:

    def __init__(self, model, max_size, *, _key=None):
        if _key is not _REGISTER_KEY:
            raise TypeError(
                "tracekit: create buffers with BufferManager().register(name, model), "
                "otherwise they are never flushed")
        self.model: type[Model] = model
        self.max_size = max_size
        self._reset()

    def _reset(self):
        self._items = []
        self._dropped = 0
        self._lock = threading.Lock()

    def add(self, obj):
        # Checked here, not at flush: one wrong object would fail the whole batch.
        if not isinstance(obj, self.model):
            raise TypeError(
                f"tracekit: {self.model.__name__} buffer got {type(obj).__name__}")
        with self._lock:
            if len(self._items) >= self.max_size:
                self._dropped += 1
                return
            self._items.append(obj)

    def flush(self):
        # Swap the list under the lock so writes happen without blocking add().
        with self._lock:
            items, self._items = self._items, []
            dropped, self._dropped = self._dropped, 0
        if dropped:
            logger.warning("tracekit: %s buffer full, dropped %d rows", self.model.__name__, dropped)
        if not items:
            return
        try:
            self.model.objects.bulk_create(items, batch_size=500)
        except (IntegrityError, DataError):
            # A bad row fails its whole batch; retry singly so only bad rows are lost.
            self._flush_one_by_one(items)
        except Exception:
            logger.exception("tracekit: failed to flush %d %s rows", len(items), self.model.__name__)

    def _flush_one_by_one(self, items):
        failed = 0
        for item in items:
            try:
                self.model.objects.bulk_create([item])
            except Exception:
                failed += 1
                if failed == 1:
                    logger.exception("tracekit: invalid %s row", self.model.__name__)
        if failed:
            logger.warning("tracekit: dropped %d invalid %s rows", failed, self.model.__name__)


class BufferManager:
    """
    Process-wide singleton owning every buffer and the flush thread.

    Started once from TracekitConfig.ready(). Forked children (gunicorn
    --preload, uwsgi) get fresh buffers and their own flush thread, since
    threads don't survive fork and the parent still owns its pending rows.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._setup()
        return cls._instance

    def _setup(self):
        self.max_size = get_setting("BUFFER_MAX_SIZE")
        self.interval = get_setting("BUFFER_FLUSH_INTERVAL")
        self._buffers = {}
        self._registry_lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._start_lock = threading.Lock()
        self.register("api_log", APILog)

    def register(self, name, model, max_size=None):
        if not isinstance(name, str) or not name:
            raise ValueError("tracekit: buffer name must be a non-empty string")
        if not (isinstance(model, type) and issubclass(model, Model)) or model._meta.abstract:
            raise TypeError(f"tracekit: {model!r} is not a concrete Django model")
        if max_size is not None and (not isinstance(max_size, int) or max_size <= 0):
            raise ValueError("tracekit: max_size must be a positive integer")

        with self._registry_lock:
            existing = self._buffers.get(name)
            if existing:
                # Same registration twice (e.g. ready() running again) is harmless.
                if existing.model is model:
                    return existing
                raise ValueError(
                    f"tracekit: buffer {name!r} is already registered "
                    f"for {existing.model.__name__}")
            buffer = Buffer(model, max_size or self.max_size, _key=_REGISTER_KEY)
            self._buffers[name] = buffer
            return buffer

    def get(self, name):
        try:
            return self._buffers[name]
        except KeyError:
            raise KeyError(
                f"tracekit: buffer {name!r} is not registered; call "
                f"BufferManager().register({name!r}, Model) first. "
                f"Registered: {sorted(self._buffers)}") from None

    @property
    def buffers(self):
        with self._registry_lock:
            return list(self._buffers.values())

    def start(self):
        with self._start_lock:
            if self._thread is not None:
                return
            self._start_thread()
            os.register_at_fork(after_in_child=self._after_fork)
            atexit.register(self.shutdown)

    def flush_all(self):
        for buffer in self.buffers:
            buffer.flush()

    def shutdown(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval)
        self.flush_all()

    def _start_thread(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="tracekit-buffer-flush", daemon=True)
        self._thread.start()

    def _after_fork(self):
        # Inherited locks may be held by the parent's thread; inherited rows
        # will be flushed by the parent. Reset in place so references
        # returned by register() stay valid.
        self._registry_lock = threading.Lock()
        self._start_lock = threading.Lock()
        for buffer in self._buffers.values():
            buffer._reset()
        self._start_thread()

    def _run(self):
        while not self._stop.wait(self.interval):
            close_old_connections()
            self.flush_all()
        close_old_connections()
