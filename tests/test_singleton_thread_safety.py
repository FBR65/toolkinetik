"""Tests for singleton thread-safety in app.py (#11)."""

from __future__ import annotations

import os
import threading

os.environ.setdefault("AGNO_API_KEY", "test-key-12345")

import pytest


@pytest.fixture
def reset_caches():
    import toolkinetik.app as app_mod
    app_mod._intent_engine = None
    app_mod._skill_writer = None
    app_mod._rag_manager = None
    yield app_mod
    app_mod._intent_engine = None
    app_mod._skill_writer = None
    app_mod._rag_manager = None


class TestSingletonThreadSafety:
    def test_get_intent_engine_thread_safe(self, reset_caches):
        from toolkinetik.app import get_intent_engine
        results = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            results.append(get_intent_engine())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All threads got the same instance
        assert len(results) == 10
        first = results[0]
        assert all(r is first for r in results), "all threads must share one instance"

    def test_get_skill_writer_thread_safe(self, reset_caches):
        from toolkinetik.app import get_skill_writer
        results = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            results.append(get_skill_writer())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is results[0] for r in results)

    def test_get_rag_manager_thread_safe(self, reset_caches):
        from toolkinetik.app import get_rag_manager
        results = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            results.append(get_rag_manager())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is results[0] for r in results)

    def test_no_deadlock_under_concurrent_load(self, reset_caches):
        from toolkinetik.app import get_intent_engine
        errors = []

        def reader():
            try:
                for _ in range(5):
                    get_intent_engine()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors
        assert all(t.is_alive() is False for t in threads)