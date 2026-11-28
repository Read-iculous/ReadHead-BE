"""Comprehension generation and single-attempt grading routes."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_current_user
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.services import quiz_service

router = APIRouter(prefix="/quiz", tags=["Comprehension Quizzes"])


@router.post("/generate")
async def generate(
    data: QuizGenerateRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Generate grounded questions with hidden answers."""
    return await quiz_service.generate(current, data)


@router.post("/{quiz_id}/submit")
async def submit(
    quiz_id: UUID,
    data: QuizSubmitRequest,
    current: Principal = Depends(get_current_user),
) -> dict:
    """Grade exactly one attempt for an owned quiz."""
    return await quiz_service.submit(current, quiz_id, data)
