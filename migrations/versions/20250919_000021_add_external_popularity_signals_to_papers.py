from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250919_000021'
down_revision = '20250827_000020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('external_popularity_signals', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('external_popularity_signals')


