from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.content.brain import VideoPackage
from src.core.config import AppSettings


@runtime_checkable
class GenerationFacade(Protocol):
    """Routing surface for local vs API generation (extended incrementally)."""

    def generate_script_package(self, *, settings: AppSettings, **kwargs: object) -> VideoPackage: ...


class _StubApiFacade:
    def generate_script_package(self, *, settings: AppSettings, **kwargs: object) -> VideoPackage:
        raise NotImplementedError("Use src.runtime.pipeline_api.run_once_api for full API runs.")


def get_generation_facade(settings: AppSettings) -> GenerationFacade:
    """Factory hook; full API execution is integrated via ``main.run_once`` → ``pipeline_api``."""
    from src.runtime.model_backend import is_api_mode

    if is_api_mode(settings):
        return _StubApiFacade()
    return _StubApiFacade()
