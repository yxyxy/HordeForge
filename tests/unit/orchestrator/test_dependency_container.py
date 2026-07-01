from __future__ import annotations

import threading
from unittest.mock import MagicMock

from orchestrator.container import DependencyContainer


class _Dummy:
    pass


def test_bind_and_resolve_returns_same_instance():
    container = DependencyContainer()
    instance = _Dummy()

    container.bind(_Dummy, instance)

    assert container.resolve(_Dummy) is instance


def test_resolve_returns_none_when_unbound():
    container = DependencyContainer()

    assert container.resolve(_Dummy) is None


def test_factory_binding_is_lazy():
    container = DependencyContainer()
    factory = MagicMock(return_value=_Dummy())

    container.register_factory(_Dummy, factory)
    factory.assert_not_called()

    container.resolve(_Dummy)
    factory.assert_called_once()


def test_factory_result_is_cached():
    container = DependencyContainer()
    created = _Dummy()
    factory = MagicMock(return_value=created)

    container.register_factory(_Dummy, factory)

    first = container.resolve(_Dummy)
    second = container.resolve(_Dummy)

    assert first is created
    assert second is created
    assert first is second
    factory.assert_called_once()


def test_explicit_binding_overrides_factory():
    container = DependencyContainer()
    instance = _Dummy()
    factory = MagicMock(return_value=_Dummy())

    container.register_factory(_Dummy, factory)
    container.bind(_Dummy, instance)

    assert container.resolve(_Dummy) is instance
    factory.assert_not_called()


def test_has_returns_true_for_bindings():
    container = DependencyContainer()
    container.bind(_Dummy, _Dummy())

    assert container.has(_Dummy) is True


def test_has_returns_true_for_factories():
    container = DependencyContainer()
    container.register_factory(_Dummy, _Dummy)

    assert container.has(_Dummy) is True


def test_has_returns_false_for_unbound():
    container = DependencyContainer()

    assert container.has(_Dummy) is False


def test_resolve_or_default_returns_default_when_unbound():
    container = DependencyContainer()
    sentinel = object()

    assert container.resolve_or_default(_Dummy, sentinel) is sentinel


def test_resolve_or_default_returns_bound_instance():
    container = DependencyContainer()
    instance = _Dummy()
    container.bind(_Dummy, instance)

    assert container.resolve_or_default(_Dummy, object()) is instance


def test_resolve_or_default_returns_default_when_factory_produces_none():
    container = DependencyContainer()
    sentinel = object()
    container.register_factory(_Dummy, lambda: None)

    assert container.resolve_or_default(_Dummy, sentinel) is sentinel


def test_clear_removes_bindings_and_factories():
    container = DependencyContainer()
    container.bind(_Dummy, _Dummy())
    container.register_factory(_Dummy, _Dummy)

    container.clear()

    assert container.has(_Dummy) is False
    assert container.resolve(_Dummy) is None
    assert container.resolve_or_default(_Dummy, "fallback") == "fallback"


def test_thread_safety_concurrent_resolve():
    container = DependencyContainer()
    call_count = 0
    lock = threading.Lock()

    def factory():
        nonlocal call_count
        with lock:
            call_count += 1
        return _Dummy()

    container.register_factory(_Dummy, factory)

    results = [None] * 20

    def worker(idx: int) -> None:
        results[idx] = container.resolve(_Dummy)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for r in results:
        assert r is not None
        assert isinstance(r, _Dummy)

    assert call_count == 1
