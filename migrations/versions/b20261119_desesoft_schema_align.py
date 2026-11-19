"""desesoft schema alignment: contacto, consentimiento y bonos

Revision ID: b20261119_align
Revises: 169a50bbea05
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b20261119_align'
down_revision: Union[str, Sequence[str], None] = '169a50bbea05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Tabla contacto
    if 'contacto' not in tables:
        op.create_table(
            'contacto',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('nombre', sa.String(length=255), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('empresa', sa.String(length=255), nullable=True),
            sa.Column('mensaje', sa.Text(), nullable=False),
            sa.Column('origen', sa.String(length=50), server_default='producto', nullable=False),
            sa.Column('tipo', sa.String(length=50), server_default='comercial', nullable=False),
            sa.Column('ip_origen', sa.String(length=50), nullable=True),
            sa.Column('creado_en', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_contacto_email', 'contacto', ['email'])
        op.create_index('ix_contacto_tipo', 'contacto', ['tipo'])

    # 2. Columnas de consentimiento en entrega_encuesta
    entrega_cols = [c['name'] for c in inspector.get_columns('entrega_encuesta')]
    if 'consentimiento_aceptado' not in entrega_cols:
        op.add_column('entrega_encuesta', sa.Column('consentimiento_aceptado', sa.Boolean(), server_default='false', nullable=True))
    if 'consentimiento_en' not in entrega_cols:
        op.add_column('entrega_encuesta', sa.Column('consentimiento_en', sa.TIMESTAMP(timezone=True), nullable=True))

    # 3. Columnas de bonificación en suscriptor
    sus_cols = [c['name'] for c in inspector.get_columns('suscriptor')]
    if 'bono_entregas' not in sus_cols:
        op.add_column('suscriptor', sa.Column('bono_entregas', sa.Integer(), server_default='0', nullable=False))
    if 'bono_paginas_ocr' not in sus_cols:
        op.add_column('suscriptor', sa.Column('bono_paginas_ocr', sa.Integer(), server_default='0', nullable=False))
    if 'bono_minutos_voz' not in sus_cols:
        op.add_column('suscriptor', sa.Column('bono_minutos_voz', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('suscriptor', 'bono_minutos_voz')
    op.drop_column('suscriptor', 'bono_paginas_ocr')
    op.drop_column('suscriptor', 'bono_entregas')

    op.drop_column('entrega_encuesta', 'consentimiento_en')
    op.drop_column('entrega_encuesta', 'consentimiento_aceptado')

    op.drop_index('ix_contacto_tipo', table_name='contacto')
    op.drop_index('ix_contacto_email', table_name='contacto')
    op.drop_table('contacto')
