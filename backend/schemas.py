from pydantic import BaseModel, Field, model_validator
from typing import Literal

KINDS = Literal['crossword', 'multiple_choice', 'matching', 'true_false', 'short_answer', 'clinical']

class Source(BaseModel):
    title: str
    section: str
    sample: bool = True
    source_id: str | None = None
    chunk_id: str | None = None
    quote: str | None = None
    material_id: str | None = None
    relative_path: str | None = None

class Question(BaseModel):
    id: str
    week: int = Field(ge=1)
    topic: str
    course: str = 'Human Anatomy and Physiology'
    kind: KINDS
    prompt: str
    prompt_zh: str
    difficulty: Literal['Foundation', 'Intermediate', 'Challenge']
    source: Source
    terms: list[str] = Field(min_length=1)
    explanation_zh: str
    answer: str | dict[str, str]
    accepted_answers: list[str] = []
    choices: list[str] = []
    pairs: list[dict[str, str]] = []
    entries: list[dict] = []
    rubric: list[str] = []
    concept_id: str | None = None
    variant_aspect: Literal['definition','terminology','mechanism','comparison','application','quantitative'] | None = None

    @model_validator(mode='after')
    def valid_payload(self):
        if self.kind == 'multiple_choice' and (len(self.choices) < 2 or self.answer not in self.choices):
            raise ValueError('Multiple choice requires choices containing the answer')
        if self.kind in ('matching', 'crossword') and not isinstance(self.answer, dict):
            raise ValueError('Structured activity requires an answer mapping')
        if self.kind == 'matching' and not self.pairs:
            raise ValueError('Matching requires pairs')
        if self.kind == 'crossword' and not self.entries:
            raise ValueError('Crossword requires entries')
        return self

