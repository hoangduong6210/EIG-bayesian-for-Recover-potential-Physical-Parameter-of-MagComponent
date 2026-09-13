"""Bounded posterior retention preserves deterministic state evaluations."""

import importlib
from pathlib import Path
import weakref

import numpy as np
import pytest


@pytest.fixture
def cache_type(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "experiments"))
    return importlib.import_module("model_mismatch_campaign").BoundedPosteriorCache


def test_lru_access_refreshes_retention(cache_type):
    cache = cache_type(max_entries=2)
    first, second, third = object(), object(), object()
    cache[("a",)] = first
    cache[("b",)] = second
    assert cache.get(("a",)) is first
    cache[("c",)] = third
    assert len(cache) == 2
    assert cache.get(("b",)) is None
    assert cache.get(("a",)) is first
    assert cache.get(("c",)) is third


def test_cache_miss_and_overwrite_do_not_evict_extra_entries(cache_type):
    cache = cache_type(max_entries=2)
    cache[("a",)] = object()
    retained = object()
    cache[("b",)] = retained
    assert cache.get(("missing",)) is None
    replacement = object()
    cache[("a",)] = replacement
    assert len(cache) == 2
    assert cache.get(("a",)) is replacement
    assert cache.get(("b",)) is retained


def test_eviction_releases_posterior_storage(cache_type):
    class Payload:
        pass

    cache = cache_type(max_entries=2)
    payload = Payload()
    reference = weakref.ref(payload)
    cache[("a",)] = payload
    del payload
    assert reference() is not None
    cache[("b",)] = Payload()
    cache[("c",)] = Payload()
    assert reference() is None


def test_bounded_cache_matches_deterministic_uncached_state_results(cache_type):
    requests = [("a",), ("b",), ("c",), ("a",), ("c",), ("d",), ("b",)]

    def evaluate(cache):
        results = []
        computed = 0
        for key in requests:
            values = cache.get(key)
            if values is None:
                # Small stand-in for the independently seeded posterior sampler.
                # Cache scheduling cannot alter this state-to-draw mapping.
                values = np.random.default_rng(ord(key[0])).normal(size=(12, 6))
                cache[key] = values
                computed += 1
            results.append(values.copy())
        return results, computed

    bounded, unbounded = cache_type(max_entries=2), {}
    bounded_values, bounded_computations = evaluate(bounded)
    unbounded_values, unbounded_computations = evaluate(unbounded)
    assert bounded_computations > unbounded_computations
    for actual, expected in zip(bounded_values, unbounded_values):
        np.testing.assert_array_equal(actual, expected)
    assert len(bounded) == 2
    assert bounded.seen_keys == set(requests)
    assert len(bounded.seen_keys) == unbounded_computations


@pytest.mark.parametrize("capacity", [0, -1, True, 2.5])
def test_invalid_cache_capacity_is_rejected(cache_type, capacity):
    with pytest.raises(ValueError, match="positive integer"):
        cache_type(max_entries=capacity)
