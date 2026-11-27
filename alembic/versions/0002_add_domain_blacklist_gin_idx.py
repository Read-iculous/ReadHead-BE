"""Add the documented privacy-domain JSONB index.

Revision ID: 0002_domain_blacklist
Revises: 0001_initial_schema
"""

from alembic import op

revision = "0002_domain_blacklist"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the domain-policy index."""
    op.create_index(
        "idx_user_settings_blacklisted_domains",
        "user_settings",
        ["blacklisted_domains"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove the domain-policy index."""
    op.drop_index("idx_user_settings_blacklisted_domains", table_name="user_settings")
