"""Batched recon: hosts are chunked so no probe/payload gets huge (Kong-scale)."""
import math

from src.workflows.recon import batches, _BATCH_SIZE


def test_batches_splits_evenly():
    assert batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_batches_single_chunk_when_small():
    assert batches([1, 2, 3], 500) == [[1, 2, 3]]


def test_batches_empty():
    assert batches([], 500) == []


def test_batches_covers_all_items_without_overlap():
    hosts = list(range(18000))          # Kong-scale
    chunks = batches(hosts, 500)
    assert len(chunks) == math.ceil(18000 / 500)   # 36 batches
    # every host appears exactly once, order preserved
    flat = [h for c in chunks for h in c]
    assert flat == hosts
    # no batch exceeds the size (so no probe/payload gets huge)
    assert all(len(c) <= 500 for c in chunks)


def test_batch_size_positive_guard():
    assert batches([1, 2, 3], 0) == [[1], [2], [3]]   # size<1 floored to 1


def test_default_batch_size():
    assert _BATCH_SIZE == 500
