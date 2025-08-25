from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250823_000017'
down_revision = '20250823_000016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('papers', sa.Column('initiated_by_user_id', sa.String(length=128), nullable=True))
    # Create index for faster lookups by initiator
    op.create_index('ix_papers_initiated_by_user_id', 'papers', ['initiated_by_user_id'])


def downgrade() -> None:
    op.drop_index('ix_papers_initiated_by_user_id', table_name='papers')
    op.drop_column('papers', 'initiated_by_user_id')
