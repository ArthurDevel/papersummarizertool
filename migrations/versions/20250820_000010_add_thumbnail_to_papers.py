from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250820_000010'
down_revision = '20250820_000009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('thumbnail_data_url', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('thumbnail_data_url')


