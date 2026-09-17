"""multiple components per issue/idea

Revision ID: a1b2c3d4e5f6
Revises: 76443bd8950a
Create Date: 2026-09-17 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '76443bd8950a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'issue_components',
        sa.Column('issue_id', sa.Integer(), nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['issue_id'], ['issues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('issue_id', 'component_id'),
    )

    op.create_table(
        'idea_components',
        sa.Column('idea_id', sa.Integer(), nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('idea_id', 'component_id'),
    )

    # Переносим уже проставленный одиночный компонент в M2M, чтобы фильтрация
    # «по любому компоненту» и отображение работали и для старых записей.
    op.execute(
        'INSERT INTO issue_components (issue_id, component_id) '
        'SELECT id, component_id FROM issues WHERE component_id IS NOT NULL'
    )
    op.execute(
        'INSERT INTO idea_components (idea_id, component_id) '
        'SELECT id, component_id FROM ideas WHERE component_id IS NOT NULL'
    )


def downgrade():
    op.drop_table('idea_components')
    op.drop_table('issue_components')
