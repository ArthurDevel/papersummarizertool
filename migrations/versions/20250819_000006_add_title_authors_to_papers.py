from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000006'
down_revision = '20250819_000005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('authors', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('authors')
        batch_op.drop_column('title')



