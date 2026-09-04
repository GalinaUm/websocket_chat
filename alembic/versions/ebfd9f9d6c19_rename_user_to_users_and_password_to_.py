"""rename user to users and password to password_hash

Revision ID: ebfd9f9d6c19
Revises: 3f91925fd772
Create Date: 2026-09-04 13:40:42.700768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ebfd9f9d6c19'
down_revision: Union[str, Sequence[str], None] = '3f91925fd772'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("user", "users")
    op.alter_column("users", "password", new_column_name="password_hash")


def downgrade() -> None:
    op.alter_column("users", "password_hash", new_column_name="password")
    op.rename_table("users", "user")
