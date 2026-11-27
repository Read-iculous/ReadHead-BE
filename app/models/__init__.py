"""Register the complete application metadata and export ORM entities."""

from app.models.api_key import UserApiKey
from app.models.auth_session import AuthSession
from app.models.conversation import Conversation, Message
from app.models.feedback import AiFeedback
from app.models.highlight import Highlight
from app.models.quiz import QuizRecord
from app.models.reading_history import ReadingHistory
from app.models.refresh_token import RefreshToken
from app.models.user import OAuthAccount, User
from app.models.user_setting import UserSetting

__all__ = [
    "UserApiKey",
    "AuthSession",
    "Conversation",
    "Message",
    "AiFeedback",
    "Highlight",
    "QuizRecord",
    "ReadingHistory",
    "RefreshToken",
    "User",
    "OAuthAccount",
    "UserSetting",
]
