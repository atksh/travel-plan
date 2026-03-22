"""add_seed_key_to_poi_master

Revision ID: 0005_add_seed_key_to_poi_master
Revises: 0004_add_unique_constraint_to_trip_candidate
Create Date: 2026-03-22 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_add_seed_key_to_poi_master"
down_revision: Union[str, None] = "0004_add_unique_constraint_to_trip_candidate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_KEY_BY_LEGACY_ID: dict[int, str] = {
    0: "start_tokyo_iriya",
    1: "nokogiri_nihonji_hell_peek",
    2: "ubara_risokyo",
    3: "oyama_senmaida",
    4: "nojimasaki_lighthouse",
    5: "haraoka_pier_okamoto",
    6: "tateyama_sunset_pier",
    7: "satomi_no_yu",
    8: "zekuu",
    9: "ryoshi_ryori_kanaya",
    10: "the_fish_bayside_kanaya",
    11: "hamano_osakana_club",
    12: "banya_honkan",
    13: "kamogawa_seaside_base",
    14: "yamato_sushi_tomiura",
    15: "kaisen_shokudo_tomiuratei",
    16: "kimura_peanuts",
    17: "michi_no_eki_tomiura_biwakurabu",
    18: "nagisa_no_eki_tateyama",
    19: "michi_no_eki_hota_shogakko",
    99: "end_tokyo_iriya",
}


def upgrade() -> None:
    with op.batch_alter_table("poi_master", schema=None) as batch_op:
        batch_op.add_column(sa.Column("seed_key", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_poi_master_seed_key", ["seed_key"])

    connection = op.get_bind()
    for legacy_id, seed_key in SEED_KEY_BY_LEGACY_ID.items():
        connection.execute(
            sa.text(
                """
                UPDATE poi_master
                SET seed_key = :seed_key
                WHERE id = :legacy_id
                  AND EXISTS (
                    SELECT 1
                    FROM poi_source_snapshot
                    WHERE poi_source_snapshot.poi_id = poi_master.id
                      AND poi_source_snapshot.source_type = 'seed'
                  )
                """
            ),
            {
                "legacy_id": legacy_id,
                "seed_key": seed_key,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("poi_master", schema=None) as batch_op:
        batch_op.drop_constraint("uq_poi_master_seed_key", type_="unique")
        batch_op.drop_column("seed_key")
