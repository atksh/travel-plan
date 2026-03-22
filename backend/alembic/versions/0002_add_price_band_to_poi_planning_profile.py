"""add_price_band_to_poi_planning_profile

Revision ID: 0002_add_price_band_to_poi_planning_profile
Revises: 0001_initial_schema
Create Date: 2026-03-21 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_add_price_band_to_poi_planning_profile"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("poi_planning_profile", schema=None) as batch_op:
        batch_op.add_column(sa.Column("price_band", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("poi_planning_profile", schema=None) as batch_op:
        batch_op.drop_column("price_band")
