"""create user table to test

Revision ID: 01
Revises:
Create Date: 2020-12-23 12:08:57.382420

"""
from alembic import op
from sqlalchemy import Column, Integer, String

# revision identifiers, used by Alembic.
revision = "01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_db_migration_user",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String, nullable=False),
    )


def downgrade():
    op.drop_table("test_db_migration_user")
