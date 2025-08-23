from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250823_000016'
down_revision = '20250823_000015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_requests', sa.Column('title', sa.String(length=512), nullable=True))
    op.add_column('user_requests', sa.Column('authors', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('user_requests', 'authors')
    op.drop_column('user_requests', 'title')


