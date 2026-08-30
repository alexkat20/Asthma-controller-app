"""per-user medicines

Revision ID: b7c1d2e3f4a5
Revises: 9654dfa3c474
Create Date: 2026-08-23

Лекарства становятся личными для каждого пользователя:
  * в medicine добавляется user_id (FK -> users.user_id);
  * уникальность medicine_name заменяется на уникальность (user_id, medicine_name);
  * существующие данные переносятся без потерь:
      1) для каждой пары (пользователь, препарат) из taken_medicine создаётся
         личная копия препарата, и записи taken_medicine перепривязываются к ней;
      2) «ничейные» препараты (добавлены, но ни разу не приняты) копируются
         каждому существующему пользователю, чтобы никто не потерял свой каталог
         (на однопользовательских базах это в точности сохраняет прежний список);
      3) старые глобальные строки (user_id IS NULL) удаляются.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c1d2e3f4a5"
down_revision = "9654dfa3c474"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) снимаем глобальную уникальность имени ДО переноса данных — иначе
    #    вставка личных копий с теми же названиями упадёт об uq_medicine_name;
    #    заодно добавляем колонку (временно nullable — старые строки её не имеют)
    with op.batch_alter_table("medicine", schema=None) as batch:
        batch.drop_constraint("uq_medicine_name", type_="unique")
        batch.add_column(sa.Column("user_id", sa.String(), nullable=True))

    conn = op.get_bind()

    # 2а) личные копии для каждой пары (пользователь, препарат) из taken_medicine
    conn.execute(
        sa.text(
            """
            INSERT INTO medicine (medicine_name, dose, user_id)
            SELECT DISTINCT m.medicine_name, m.dose, tm.user_id
            FROM medicine m
            JOIN taken_medicine tm ON tm.medicine_id = m.medicine_id
            WHERE m.user_id IS NULL
            """
        )
    )

    # 2б) перепривязка taken_medicine со старых глобальных строк на личные копии
    conn.execute(
        sa.text(
            """
            UPDATE taken_medicine
            SET medicine_id = (
                SELECT m2.medicine_id
                FROM medicine m2
                JOIN medicine m1 ON m1.medicine_id = taken_medicine.medicine_id
                WHERE m2.user_id = taken_medicine.user_id
                  AND lower(m2.medicine_name) = lower(m1.medicine_name)
                  AND m2.user_id IS NOT NULL
            )
            WHERE (
                SELECT m0.user_id FROM medicine m0
                WHERE m0.medicine_id = taken_medicine.medicine_id
            ) IS NULL
            """
        )
    )

    # 2в) «ничейные» препараты — каждому существующему пользователю,
    #     без дублей, если личная копия уже создана шагом 2а
    conn.execute(
        sa.text(
            """
            INSERT INTO medicine (medicine_name, dose, user_id)
            SELECT m.medicine_name, m.dose, u.user_id
            FROM medicine m
            CROSS JOIN users u
            WHERE m.user_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM medicine d
                  WHERE d.user_id = u.user_id
                    AND lower(d.medicine_name) = lower(m.medicine_name)
              )
            """
        )
    )

    # 2г) глобальные строки больше не нужны
    conn.execute(sa.text("DELETE FROM medicine WHERE user_id IS NULL"))

    # 3) затягиваем гайки: batch-режим ради SQLite (пересоздание таблицы),
    #    на PostgreSQL Alembic выполнит обычные ALTER
    with op.batch_alter_table("medicine", schema=None) as batch:
        batch.alter_column("user_id", existing_type=sa.String(), nullable=False)
        batch.create_unique_constraint(
            "uq_medicine_user_name", ["user_id", "medicine_name"]
        )
        batch.create_foreign_key(
            "fk_medicine_user_id_users", "users", ["user_id"], ["user_id"]
        )


def downgrade() -> None:
    # Сворачиваем обратно в глобальный каталог: по одному препарату на имя
    # (минимальный medicine_id), taken_medicine перепривязывается на него.
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE taken_medicine
            SET medicine_id = (
                SELECT MIN(m2.medicine_id)
                FROM medicine m2
                JOIN medicine m1 ON m1.medicine_id = taken_medicine.medicine_id
                WHERE lower(m2.medicine_name) = lower(m1.medicine_name)
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM medicine
            WHERE medicine_id NOT IN (
                SELECT MIN(medicine_id) FROM medicine GROUP BY lower(medicine_name)
            )
            """
        )
    )

    with op.batch_alter_table("medicine", schema=None) as batch:
        batch.drop_constraint("fk_medicine_user_id_users", type_="foreignkey")
        batch.drop_constraint("uq_medicine_user_name", type_="unique")
        batch.create_unique_constraint("uq_medicine_name", ["medicine_name"])
        batch.drop_column("user_id")
