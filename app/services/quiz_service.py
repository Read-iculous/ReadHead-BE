"""Grounded quiz generation, hidden answer storage and atomic single grading."""

import json
from uuid import UUID, uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core import redis
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.models.quiz import QuizRecord
from app.schemas.quiz import GeneratedQuiz, QuizGenerateRequest, QuizSubmitRequest
from app.services.ai_service import complete_source
from app.services.common import lock_user, settings_for


async def generate(principal: Principal, data: QuizGenerateRequest) -> dict:
    """Generate validated multiple choice questions without exposing answer keys."""
    if len(data.page_text.split()) < 20:
        raise AppException(
            422,
            "UNREPRESENTATIVE_SOURCE",
            "Provide at least 20 words of representative source text",
        )
    async with transaction() as db:
        private = (await settings_for(db, principal.user_id)).privacy_mode_enabled
    if private:
        try:
            await redis.client.ping()
        except RedisError as exc:
            raise AppException(
                503, "SERVICE_DEGRADED", "Private quizzes require temporary caching"
            ) from exc
    instruction = 'Return ONLY JSON: {"questions":[{"question_id":1,"question_text":"...","options":["...","...","...","..."],"correct_option":0,"explanation":"...source evidence..."}]}. Generate 3 to 5 questions with unique IDs 1..5, exactly 4 options, zero-based correct_option. Use only the page; no invented facts.'
    raw = await complete_source(
        principal, data.page_url, data.page_text, instruction, data.bypass_protection
    )
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.splitlines()[1:-1])
        quiz = GeneratedQuiz.model_validate_json(clean)
        questions = [q.model_dump() for q in quiz.questions]
        if len({q["question_id"] for q in questions}) != len(questions):
            raise ValueError()
    except (ValueError, ValidationError) as exc:
        raise AppException(
            502,
            "UPSTREAM_AI_ERROR",
            "Provider returned an invalid quiz; retry manually",
        ) from exc
    qid = uuid4()
    async with transaction() as db:
        # Every cache write shares deletion's user lock, including initially private requests.
        await lock_user(db, principal.user_id)
        from app.services.auth_service import checked_session

        await checked_session(db, principal.user_id, principal.session_id, False)
        if private or (await settings_for(db, principal.user_id)).privacy_mode_enabled:
            if not await redis.cache_private_quiz(
                str(principal.user_id),
                str(qid),
                dict(
                    user_id=str(principal.user_id), questions=questions, submitted=False
                ),
            ):
                raise AppException(
                    503, "SERVICE_DEGRADED", "Private quiz cache is unavailable"
                )
        else:
            db.add(
                QuizRecord(
                    id=qid,
                    user_id=principal.user_id,
                    page_url=data.page_url,
                    questions_payload=questions,
                )
            )
    return {
        "data": dict(
            quiz_id=qid,
            questions=[
                {
                    k: v
                    for k, v in q.items()
                    if k not in {"correct_option", "explanation"}
                }
                for q in questions
            ],
        )
    }


def grade(questions: list[dict], answers: dict) -> dict:
    """Validate every question/option and produce deterministic review feedback."""
    expected = {str(q["question_id"]) for q in questions}
    if set(answers) != expected or any(
        type(v) is not int or not 0 <= v < 4 for v in answers.values()
    ):
        raise AppException(
            422,
            "VALIDATION_ERROR",
            "Submit one option index (0..3) for every question",
            "answers",
        )
    review = [
        dict(
            question_id=q["question_id"],
            selected_option=answers[str(q["question_id"])],
            correct_option=q["correct_option"],
            is_correct=answers[str(q["question_id"])] == q["correct_option"],
            explanation=q["explanation"],
        )
        for q in questions
    ]
    return dict(
        score=sum(r["is_correct"] for r in review), total=len(review), review=review
    )


async def submit(principal: Principal, qid: UUID, data: QuizSubmitRequest) -> dict:
    """Grade once, enforcing owner isolation for both persistent and private quizzes."""
    async with transaction() as db:
        row = await db.scalar(
            select(QuizRecord)
            .where(QuizRecord.id == qid, QuizRecord.user_id == principal.user_id)
            .with_for_update()
        )
        if row:
            if row.score is not None:
                raise AppException(
                    400,
                    "QUIZ_ALREADY_SUBMITTED",
                    "Quiz has already been submitted and graded",
                )
            result = grade(row.questions_payload, data.answers)
            row.user_answers = data.answers
            row.score = result["score"]
            return {"data": result}
    key = f"ephemeral_quiz:{qid}"
    try:
        raw = await redis.client.get(key)
        if not raw:
            raise AppException(404, "QUIZ_NOT_FOUND", "Quiz not found or expired")
        cached = json.loads(raw)
        if cached.get("user_id") != str(principal.user_id):
            raise AppException(404, "QUIZ_NOT_FOUND", "Quiz not found")
        if cached.get("submitted"):
            raise AppException(
                400,
                "QUIZ_ALREADY_SUBMITTED",
                "Quiz has already been submitted and graded",
            )
        result = grade(cached["questions"], data.answers)
        cached["submitted"] = True
        script = "if redis.call('get',KEYS[1]) ~= ARGV[1] then return 0 end local ttl=redis.call('pttl',KEYS[1]); if ttl <= 0 then return 0 end redis.call('psetex',KEYS[1],ttl,ARGV[2]); return 1"
        if not await redis.client.eval(script, 1, key, raw, json.dumps(cached)):
            raise AppException(
                400,
                "QUIZ_ALREADY_SUBMITTED",
                "Quiz has already been submitted or expired",
            )
        return {"data": result}
    except RedisError as exc:
        raise AppException(
            503, "SERVICE_DEGRADED", "Private quiz cache is unavailable"
        ) from exc
