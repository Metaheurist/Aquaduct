"""Video script LLM package (local transformers + shared prompt/package helpers).

Re-exports all public and underscore-prefixed names from submodules (matches legacy ``_monolith`` surface).
"""

from __future__ import annotations

from . import api as _brain_api
from . import package as _brain_package
from . import prompts as _brain_prompts
from . import runtime as _brain_runtime

_m = globals()
for _src in (_brain_package, _brain_prompts, _brain_runtime, _brain_api):
    for _k, _v in vars(_src).items():
        if _k.startswith("__"):
            continue
        _m[_k] = _v

del _brain_api, _brain_package, _brain_prompts, _brain_runtime, _m, _src, _k, _v
