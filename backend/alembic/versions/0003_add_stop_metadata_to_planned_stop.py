"""add_stop_metadata_to_planned_stop

Revision ID: 0003_add_stop_metadata_to_planned_stop
Revises: 0002_add_price_band_to_poi_planning_profile
Create Date: 2026-03-22 00:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_add_stop_metadata_to_planned_stop"
down_revision: Union[str, None] = "0002_add_price_band_to_poi_planning_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("planned_stop", schema=None) as batch_op:
        batch_op.add_column(sa.Column("label", sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column("lat", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("lng", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("planned_stop", schema=None) as batch_op:
        batch_op.drop_column("lng")
        batch_op.drop_column("lat")
        batch_op.drop_column("label")
