from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250820_000007'
down_revision = '20250819_000006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'requested_papers',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('arxiv_id', sa.String(length=64), nullable=False, unique=True),
        sa.Column('arxiv_abs_url', sa.String(length=255), nullable=False),
        sa.Column('arxiv_pdf_url', sa.String(length=255), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('first_requested_at', sa.DateTime(), nullable=False),
        sa.Column('last_requested_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('requested_papers')



