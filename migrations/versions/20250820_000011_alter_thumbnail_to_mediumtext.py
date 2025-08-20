from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '20250820_000011'
down_revision = '20250820_000010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.alter_column('thumbnail_data_url', type_=mysql.MEDIUMTEXT())


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.alter_column('thumbnail_data_url', type_=sa.Text())


