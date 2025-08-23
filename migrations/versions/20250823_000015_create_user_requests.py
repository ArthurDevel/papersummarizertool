from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250823_000015'
down_revision = '20250823_000014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_requests',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('arxiv_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_requests_user', ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'arxiv_id', name='uq_user_requests_user_arxiv'),
    )
    op.create_index('ix_user_requests_user_id', 'user_requests', ['user_id'])
    op.create_index('ix_user_requests_arxiv_id', 'user_requests', ['arxiv_id'])


def downgrade() -> None:
    op.drop_index('ix_user_requests_arxiv_id', table_name='user_requests')
    op.drop_index('ix_user_requests_user_id', table_name='user_requests')
    op.drop_table('user_requests')


