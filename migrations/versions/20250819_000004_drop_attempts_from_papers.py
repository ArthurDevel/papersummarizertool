from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000004'
down_revision = '20250819_000003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        try:
            batch_op.drop_column('attempts')
        except Exception:
            # Column may already be absent
            pass


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))


