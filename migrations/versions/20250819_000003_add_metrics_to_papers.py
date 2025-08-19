from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000003'
down_revision = '20250819_000002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('num_pages', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('processing_time_seconds', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('total_cost', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('avg_cost_per_page', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('avg_cost_per_page')
        batch_op.drop_column('total_cost')
        batch_op.drop_column('processing_time_seconds')
        batch_op.drop_column('num_pages')


