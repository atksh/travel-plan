"""add_unique_constraint_to_trip_candidate

Revision ID: 0004_add_unique_constraint_to_trip_candidate
Revises: 0003_add_stop_metadata_to_planned_stop
Create Date: 2026-03-22 16:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_add_unique_constraint_to_trip_candidate"
down_revision: Union[str, None] = "0003_add_stop_metadata_to_planned_stop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_row = connection.execute(
        sa.text(
            """
            SELECT trip_id, poi_id, COUNT(*) AS duplicate_count
            FROM trip_candidate
            GROUP BY trip_id, poi_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_row is not None:
        raise RuntimeError(
            "Duplicate trip_candidate rows detected; clean up duplicates before "
            "applying the unique constraint on (trip_id, poi_id)."
        )

    with op.batch_alter_table("trip_candidate", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_trip_candidate_trip_id_poi_id",
            ["trip_id", "poi_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trip_candidate", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_trip_candidate_trip_id_poi_id",
            type_="unique",
        )
