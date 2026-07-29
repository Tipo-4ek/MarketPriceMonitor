"""Initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tg_user_id', sa.BigInteger(), nullable=False),
        sa.Column('locale', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_tg_user_id'), 'users', ['tg_user_id'], unique=True)

    # Create products table
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            'provider',
            sa.Enum('OZON', 'WILDBERRIES', name='providerenum'),
            nullable=False,
        ),
        sa.Column('url', sa.String(length=1024), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('last_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', 'provider', name='uq_product_url_provider'),
    )
    op.create_index(op.f('ix_products_provider'), 'products', ['provider'], unique=False)

    # Create trackings table
    op.create_table(
        'trackings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('custom_threshold_delta', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trackings_product_id'), 'trackings', ['product_id'], unique=False)
    op.create_index(op.f('ix_trackings_user_id'), 'trackings', ['user_id'], unique=False)

    # Create price_history table
    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_price_history_product_id'), 'price_history', ['product_id'], unique=False)
    op.create_index(op.f('ix_price_history_timestamp'), 'price_history', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_price_history_timestamp'), table_name='price_history')
    op.drop_index(op.f('ix_price_history_product_id'), table_name='price_history')
    op.drop_table('price_history')
    op.drop_index(op.f('ix_trackings_user_id'), table_name='trackings')
    op.drop_index(op.f('ix_trackings_product_id'), table_name='trackings')
    op.drop_table('trackings')
    op.drop_index(op.f('ix_products_provider'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_users_tg_user_id'), table_name='users')
    op.drop_table('users')
    # Postgres keeps the enum type after the table is gone; SQLite has no
    # such type, so the statement is dialect-guarded.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TYPE providerenum')
