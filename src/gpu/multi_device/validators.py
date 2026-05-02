from __future__ import annotations


def clamp_device_index(idx: int, *, valid_indices: frozenset[int] | None) -> int:
    """Clamp ``idx`` to a known-good CUDA ordinal; fall back to 0."""
    try:
        i = int(idx)
    except Exception:
        i = 0
    if valid_indices is not None and valid_indices:
        if i in valid_indices:
            return i
        return sorted(valid_indices)[0]
    return max(0, i)


def first_peer_index(primary: int, n_cuda: int) -> int | None:
    """Return another CUDA ordinal when ``n_cuda >= 2``."""
    nc = max(0, int(n_cuda))
    if nc < 2:
        return None
    for i in range(nc):
        if i != int(primary):
            return int(i)
    return None


def cuda_index_set(count: int) -> frozenset[int]:
    c = max(0, int(count))
    return frozenset(range(c))
