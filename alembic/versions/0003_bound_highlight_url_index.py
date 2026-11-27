"""Bound highlight URL index entries with a digest and preserve exact URL checks.

Revision ID: 0003_highlight_url_digest
Revises: 0002_domain_blacklist
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_highlight_url_digest"
down_revision = "0002_domain_blacklist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace the unbounded URL key without changing stored URLs or ownership."""
    op.drop_index("idx_highlights_user_url", table_name="highlights")
    op.create_index(
        "idx_highlights_user_url", "highlights", ["user_id", sa.text("md5(page_url)")]
    )


def downgrade() -> None:
    """Restore the old index; long URLs must be exported/removed before rollback."""
    op.drop_index("idx_highlights_user_url", table_name="highlights")
    op.create_index("idx_highlights_user_url", "highlights", ["user_id", "page_url"])
