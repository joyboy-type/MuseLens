from pathlib import Path

from muselens.index import IndexedImage, SearchHit
from muselens.reranker import (
    QwenVLReranker,
    _nested_lists_to_tensors,
    rerank_candidates,
)


class FakeTorch:
    @staticmethod
    def tensor(value):
        return ("tensor", value)


def test_nested_processor_lists_are_tensorized() -> None:
    inputs = {"input_ids": "already-a-tensor", "mm_token_type_ids": [[1, 2]]}
    converted = _nested_lists_to_tensors(inputs, FakeTorch())
    assert converted["input_ids"] == "already-a-tensor"
    assert converted["mm_token_type_ids"] == ("tensor", [[1, 2]])


def test_qwen_messages_include_query_and_local_image_uri(tmp_path: Path) -> None:
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"not decoded by this pure formatting test")
    messages = QwenVLReranker()._messages("一只狗", image)
    content = messages[1]["content"]
    assert content[1]["text"] == "<Query>: 一只狗"
    assert content[3]["image"] == image.resolve().as_uri()


def test_rerank_candidates_sorts_and_rejects_below_threshold(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    candidates = [
        (SearchHit(IndexedImage("1", "first.jpg", "image/jpeg"), 0.9), first),
        (SearchHit(IndexedImage("2", "second.jpg", "image/jpeg"), 0.8), second),
    ]

    class Scorer:
        def score(self, query, paths):
            assert query == "dog"
            assert paths == [first, second]
            return [0.2, 0.7]

    ranked = rerank_candidates(
        "dog",
        candidates,
        lambda stored: stored,
        Scorer(),
        min_score=0.4,
        recall_k=5,
    )
    assert [(hit.image.image_id, hit.score) for hit, _ in ranked] == [("2", 0.7)]
