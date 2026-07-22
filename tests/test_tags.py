import numpy as np

from muselens.tags import TagDefinition, ZeroShotTagger


class FakeTextEncoder:
    model_id = "fake-siglip"

    def __init__(self) -> None:
        self.calls = 0

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        vectors = {
            "dog": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
            "cat": np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
            "city": np.asarray([0.0, 0.0, 1.0], dtype=np.float32),
        }
        return np.stack([vectors[text] for text in texts])


DEFINITIONS = (
    TagDefinition("dog", "狗", "dog", "subject"),
    TagDefinition("cat", "猫", "cat", "subject"),
    TagDefinition("city", "城市", "city", "scene"),
)


def test_zero_shot_tagger_uses_embedding_similarity_and_caches_texts() -> None:
    encoder = FakeTextEncoder()
    tagger = ZeroShotTagger(encoder, DEFINITIONS, min_score=0.12, relative_margin=0.04)

    first = tagger.predict(np.asarray([0.05, 0.95, 0.0], dtype=np.float32))
    second = tagger.predict(np.asarray([1.0, 0.0, 0.0], dtype=np.float32))

    assert [tag.slug for tag in first] == ["dog"]
    assert first[0].label == "狗"
    assert [tag.slug for tag in second] == ["cat"]
    assert encoder.calls == 1
    assert tagger.model_id == "fake-siglip:tags-v1"


def test_zero_shot_tagger_can_abstain_when_every_score_is_weak() -> None:
    tagger = ZeroShotTagger(FakeTextEncoder(), DEFINITIONS, min_score=0.12)

    tags = tagger.predict(np.asarray([0.0, 0.0, -1.0], dtype=np.float32))

    assert tags == ()
