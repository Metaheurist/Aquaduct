"""Topic grounding tag batching (VRAM / token friendly)."""

from src.content.brain import TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK, topic_grounding_pair_chunks


def test_topic_grounding_pair_chunks_default_size() -> None:
    pairs = [(str(i), f"D{i}") for i in range(TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK + 2)]
    chunks = topic_grounding_pair_chunks(pairs)
    assert len(chunks) == 2
    assert len(chunks[0]) == TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK
    assert len(chunks[1]) == 2


def test_topic_grounding_pair_chunks_custom_size_and_empty() -> None:
    assert topic_grounding_pair_chunks([], chunk_size=3) == []
    p = [("a", "A"), ("b", "B"), ("c", "C")]
    assert topic_grounding_pair_chunks(p, chunk_size=1) == [[("a", "A")], [("b", "B")], [("c", "C")]]
    assert topic_grounding_pair_chunks(p, chunk_size=10) == [p]
