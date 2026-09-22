"""rename learning session mode to session_type

Revision ID: c6abc5738cdd
Revises: 11f51236688d
Create Date: 2026-09-15 22:22:49.964878

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6abc5738cdd'
down_revision: Union[str, Sequence[str], None] = '11f51236688d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A real rename (not drop+add) -- preserves any existing rows'
    # values instead of losing them. Gamify/Serious dual mode was
    # removed from the app's design, and this column's role has
    # shifted to distinguishing For You sessions from Drill sessions.
    op.alter_column('learning_sessions', 'mode', new_column_name='session_type')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('learning_sessions', 'session_type', new_column_name='mode')
