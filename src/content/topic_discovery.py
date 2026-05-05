from src.content.topics.discovery import *  # noqa: F403

# Star import does not re-export underscore names; tests and legacy callers rely on this helper.
from src.content.topics.discovery import _should_discard_creative_candidate as _should_discard_creative_candidate
