"""Source-grounded comprehension quiz input and model output."""

from pydantic import Field, StrictInt, field_validator

from app.schemas.common import PageSource, PostgresText, RequestModel, utf8


class QuizGenerateRequest(PageSource):
    """Create a source-grounded quiz with hidden answer keys."""

    page_text: str = Field(min_length=1)
    bypass_protection: bool = False

    @field_validator("page_text")
    @classmethod
    def source_limit(cls, value: str) -> str:
        return utf8(value, 102400)


class QuizSubmitRequest(RequestModel):
    """One option index per generated question ID."""

    answers: dict[str, StrictInt] = Field(min_length=1, max_length=5)


class GeneratedQuestion(RequestModel):
    """Validated server-only model output before answer redaction."""

    question_id: int = Field(strict=True, ge=1, le=5)
    question_text: PostgresText = Field(min_length=1, max_length=2000)
    options: list[PostgresText] = Field(min_length=4, max_length=4)
    correct_option: int = Field(strict=True, ge=0, le=3)
    explanation: PostgresText = Field(min_length=1, max_length=4000)


class GeneratedQuiz(RequestModel):
    """Strict generated quiz structure."""

    questions: list[GeneratedQuestion] = Field(min_length=3, max_length=5)
