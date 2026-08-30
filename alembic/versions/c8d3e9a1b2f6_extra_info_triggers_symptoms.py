"""extra_info: more triggers + symptoms

Revision ID: c8d3e9a1b2f6
Revises: b7c1d2e3f4a5
Create Date: 2026-08-30

Расширяет extra_info новыми колонками-флагами:
  * триггеры: weather, smoke, strong_smells, pets, dust, menstrual_cycle;
  * симптомы: dyspnea, cough, wheezing, chest_tightness, nocturnal_symptoms.

Все — Boolean NOT NULL DEFAULT false, поэтому существующие строки получают
False автоматически (server_default), без ручного backfill.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d3e9a1b2f6"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None

NEW_COLUMNS = [
    "weather",
    "smoke",
    "strong_smells",
    "pets",
    "dust",
    "menstrual_cycle",
    "dyspnea",
    "cough",
    "wheezing",
    "chest_tightness",
    "nocturnal_symptoms",
]


def upgrade() -> None:
    with op.batch_alter_table("extra_info", schema=None) as batch:
        for name in NEW_COLUMNS:
            batch.add_column(
                sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false())
            )


def downgrade() -> None:
    with op.batch_alter_table("extra_info", schema=None) as batch:
        for name in NEW_COLUMNS:
            batch.drop_column(name)
