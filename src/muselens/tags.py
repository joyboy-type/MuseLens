from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .index import normalize


@dataclass(frozen=True)
class TagDefinition:
    slug: str
    label: str
    prompt: str
    group: str


@dataclass(frozen=True)
class ImageTag:
    slug: str
    label: str
    score: float
    source: str = "auto"


DEFAULT_TAGS = (
    TagDefinition("person", "人物", "A photo of a person.", "subject"),
    TagDefinition("dog", "狗", "A photo of a dog.", "subject"),
    TagDefinition("cat", "猫", "A photo of a cat.", "subject"),
    TagDefinition("bird", "鸟", "A photo of a bird.", "subject"),
    TagDefinition("wildlife", "野生动物", "A photo of a wild animal.", "subject"),
    TagDefinition("elephant", "大象", "A photo of an elephant.", "subject"),
    TagDefinition("cow", "牛", "A photo of a cow.", "subject"),
    TagDefinition("horse", "马", "A photo of a horse.", "subject"),
    TagDefinition("sheep", "羊", "A photo of a sheep.", "subject"),
    TagDefinition("giraffe", "长颈鹿", "A photo of a giraffe.", "subject"),
    TagDefinition("flower", "花卉", "A photo of flowers.", "subject"),
    TagDefinition("food", "美食", "A photo of food or a meal.", "subject"),
    TagDefinition("car", "汽车", "A photo of a car.", "subject"),
    TagDefinition("bus", "公交车", "A photo of a bus.", "subject"),
    TagDefinition("airplane", "飞机", "A photo of an airplane.", "subject"),
    TagDefinition("bicycle", "自行车", "A photo of a bicycle.", "subject"),
    TagDefinition("motorcycle", "摩托车", "A photo of a motorcycle.", "subject"),
    TagDefinition("boat", "船", "A photo of a boat or ship.", "subject"),
    TagDefinition("building", "建筑", "A photo of a building.", "subject"),
    TagDefinition("pizza", "披萨", "A photo of pizza.", "subject"),
    TagDefinition("cake", "蛋糕", "A photo of a cake.", "subject"),
    TagDefinition("sports-ball", "球", "A photo of a sports ball.", "subject"),
    TagDefinition("snowboard", "滑雪板", "A photo of a snowboard.", "subject"),
    TagDefinition("laptop", "笔记本电脑", "A photo of a laptop computer.", "subject"),
    TagDefinition("cell-phone", "手机", "A photo of a cell phone.", "subject"),
    TagDefinition("book", "书", "A photo of a book.", "subject"),
    TagDefinition("clock", "时钟", "A photo of a clock.", "subject"),
    TagDefinition("beach", "海滩", "A photo taken at a beach.", "scene"),
    TagDefinition("mountain", "山景", "A photo of mountains.", "scene"),
    TagDefinition("forest", "森林", "A photo taken in a forest.", "scene"),
    TagDefinition("city", "城市", "A photo of a city street.", "scene"),
    TagDefinition("indoor", "室内", "A photo taken indoors.", "scene"),
    TagDefinition("night", "夜景", "A photo taken at night.", "scene"),
    TagDefinition("snow", "雪景", "A photo of a snowy scene.", "scene"),
    TagDefinition("water", "水景", "A photo featuring water.", "scene"),
    TagDefinition("sunset", "日落", "A photo of a sunset.", "scene"),
    TagDefinition("sports", "运动", "A photo of sports or exercise.", "activity"),
    TagDefinition("travel", "旅行", "A travel photograph.", "activity"),
    TagDefinition("close-up", "特写", "A close-up photograph.", "style"),
    TagDefinition("nature", "自然", "A photograph of nature.", "style"),
)


class TextEncoder(Protocol):
    model_id: str

    def encode_texts(self, texts: list[str]) -> np.ndarray: ...


class ZeroShotTagger:
    """Assign a small controlled vocabulary directly from image embeddings."""

    vocabulary_version = "tags-v1"

    def __init__(
        self,
        encoder: TextEncoder,
        definitions: tuple[TagDefinition, ...] = DEFAULT_TAGS,
        *,
        min_score: float = 0.05,
        relative_margin: float = 0.04,
        max_tags: int = 3,
    ) -> None:
        if not definitions:
            raise ValueError("Tag vocabulary cannot be empty.")
        if max_tags < 1:
            raise ValueError("max_tags must be positive.")
        self.encoder = encoder
        self.definitions = definitions
        self.min_score = min_score
        self.relative_margin = relative_margin
        self.max_tags = max_tags
        self.model_id = f"{encoder.model_id}:{self.vocabulary_version}"
        self._text_matrix: np.ndarray | None = None

    def predict(self, image_vector: np.ndarray) -> tuple[ImageTag, ...]:
        scores = self._text_vectors() @ normalize(image_vector)
        order = np.argsort(-scores, kind="stable")
        best_score = float(scores[order[0]])
        threshold = max(self.min_score, best_score - self.relative_margin)
        selected = [position for position in order if scores[position] >= threshold][
            : self.max_tags
        ]
        return tuple(
            ImageTag(
                slug=self.definitions[int(position)].slug,
                label=self.definitions[int(position)].label,
                score=float(scores[position]),
            )
            for position in selected
        )

    def _text_vectors(self) -> np.ndarray:
        if self._text_matrix is None:
            vectors = self.encoder.encode_texts(
                [definition.prompt for definition in self.definitions]
            )
            self._text_matrix = np.stack([normalize(vector) for vector in vectors])
        return self._text_matrix
