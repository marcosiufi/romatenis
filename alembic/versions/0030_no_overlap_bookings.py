"""impede reserva dupla no nivel do banco (EXCLUDE por intervalo)

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-30

A validacao de sobreposicao existia so na aplicacao (SELECT antes do INSERT),
deixando uma janela de corrida: duas requisicoes simultaneas para o mesmo
horario passavam as duas. Com 2 workers uvicorn isso e alcancavel — sobretudo
na janela de ultima hora, quando varios membros disputam um slot liberado.

A constraint EXCLUDE resolve no banco, entao nenhuma corrida escapa,
independente do numero de workers. Usa tstzrange para cobrir tambem locacoes
de 2 a 4 horas, que o indice por hora de inicio nao pegaria.

Cuidado com o predicado: o PostgreSQL exige funcoes IMMUTABLE em predicado de
indice, e `status::text` e apenas STABLE (rotulos de enum podem ser renomeados).
Por isso a comparacao e feita direto com os literais do enum, sem cast.
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

# Reservas nestes status "seguram" o horario
STATUS_ATIVOS = "('confirmada', 'aguardando_pagamento')"


def upgrade() -> None:
    # Falha cedo e com mensagem clara se ja houver sobreposicao em producao
    op.execute(f"""
    DO $$
    DECLARE conflitos int;
    BEGIN
        SELECT COUNT(*) INTO conflitos
        FROM bookings a
        JOIN bookings b
          ON a.id < b.id
         AND a.data_hora_inicio < b.data_hora_fim
         AND b.data_hora_inicio < a.data_hora_fim
        WHERE a.status IN {STATUS_ATIVOS}
          AND b.status IN {STATUS_ATIVOS};

        IF conflitos > 0 THEN
            RAISE EXCEPTION
              'Existem % par(es) de reservas sobrepostas. Cancele as duplicadas antes de aplicar a 0030.',
              conflitos;
        END IF;
    END $$;
    """)

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(f"""
        ALTER TABLE bookings
        ADD CONSTRAINT bookings_sem_sobreposicao
        EXCLUDE USING gist (
            tstzrange(data_hora_inicio, data_hora_fim) WITH &&
        )
        WHERE (status IN {STATUS_ATIVOS})
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_sem_sobreposicao")
