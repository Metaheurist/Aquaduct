"""
VRAM-first intra-stage placement (registry + planners).

Shard mode ``vram_first_auto`` plus Auto CUDA routing enables these code paths when
CUDA device count is at least two and quant/environment gates permit.
"""
from src.gpu.multi_device.registry import ShardRegistryRow, lookup_shard_row, normalize_hub_repo_id

__all__ = ["ShardRegistryRow", "lookup_shard_row", "normalize_hub_repo_id"]
