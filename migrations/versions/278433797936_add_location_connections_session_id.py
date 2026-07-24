"""add location_connections session_id

Revision ID: 278433797936
Revises: c7315b44fd5d
Create Date: 2026-07-24 18:51:29.195680

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '278433797936'
down_revision: Union[str, Sequence[str], None] = 'c7315b44fd5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('location_connections', sa.Column('session_id', sa.Integer(), nullable=False, comment='Игровая сессия'))
    op.create_foreign_key('fk_loc_conn_session', 'location_connections', 'game_sessions', ['session_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_loc_conn_session', 'location_connections', type_='foreignkey')
    op.drop_column('location_connections', 'session_id')
