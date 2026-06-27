"""clausulas editaveis do contrato de adesao

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_CLAUSULAS = [
    (1, "1. IDENTIFICAÇÃO DAS PARTES",
     "CONTRATANTE: Rosangela Pioli Siufi 05405791814, inscrita no CNPJ sob o n.º 29.616.848/0001-21, "
     "nome fantasia Roma Tênis, doravante denominada ESTABELECIMENTO.\n"
     "CONTRATADO(A): O(a) cliente identificado(a) no ato da adesão eletrônica, doravante denominado(a) CLIENTE."),

    (2, "2. OBJETO DO CONTRATO",
     "Este instrumento regula a adesão do CLIENTE ao serviço de uso das instalações esportivas da Roma Tênis "
     "para fins recreativos, podendo incluir participação no ranking interno e/ou locação avulsa de quadras. "
     "O CLIENTE não é sócio do ESTABELECIMENTO, sendo tratado exclusivamente como usuário do espaço para fins "
     "de lazer e recreação."),

    (3, "3. PLANOS E PAGAMENTO",
     "3.1. O CLIENTE escolherá, no ato da adesão, um dos planos disponíveis: Mensal, Trimestral ou Anual.\n"
     "3.2. O pagamento poderá ser realizado via PIX à vista, com desconto de 5% (cinco por cento) sobre o valor "
     "total, ou parcelado de acordo com o plano escolhido: Trimestral em até 3 (três) parcelas ou Anual em até "
     "12 (doze) parcelas.\n"
     "3.3. O link de pagamento será enviado ao CLIENTE via e-mail pela plataforma ASAAS.\n"
     "3.4. O atraso no pagamento superior a 7 (sete) dias corridos acarretará na suspensão automática do acesso "
     "ao ranking e à reserva de quadras, sem prejuízo da cobrança dos valores devidos."),

    (4, "4. UTILIZAÇÃO DAS INSTALAÇÕES",
     "4.1. O CLIENTE obriga-se a respeitar os horários reservados e demais usuários, mantendo postura respeitosa "
     "e colaborativa dentro do ESTABELECIMENTO.\n"
     "4.2. O CLIENTE utilizará as quadras exclusivamente para o horário e modalidade contratados, não podendo "
     "ceder ou transferir sua reserva a terceiros.\n"
     "4.3. O CLIENTE é responsável por comparecer nos horários agendados. Faltas injustificadas repetidas poderão "
     "resultar em penalidades conforme previsto neste contrato.\n"
     "4.4. Pré-reserva e expiração (aplicável apenas para locações avulsas): a pré-reserva expirará "
     "automaticamente em 10 (dez) minutos caso o pagamento não seja confirmado dentro desse prazo."),

    (5, "5. RANKING E COMPETIÇÃO",
     "5.1. A participação no ranking é limitada a 30 (trinta) jogadores ativos simultaneamente.\n"
     "5.2. Os jogos do ranking seguem calendário definido pelo ESTABELECIMENTO, podendo ser alterado conforme "
     "necessidade operacional.\n"
     "5.3. Resultados e estatísticas das partidas poderão ser publicados no sistema interno do ESTABELECIMENTO."),

    (6, "6. CONDUTA E CONVIVÊNCIA",
     "6.1. O CLIENTE compromete-se a manter comportamento respeitoso com todos os usuários, funcionários e "
     "prestadores de serviço do ESTABELECIMENTO.\n"
     "6.2. São expressamente proibidos: discussões, brigas, ofensas verbais ou físicas, linguagem inadequada e "
     "qualquer forma de assédio ou discriminação.\n"
     "6.3. O descumprimento das normas de conduta poderá resultar em suspensão imediata do plano sem reembolso, "
     "a critério exclusivo do ESTABELECIMENTO.\n"
     "6.4. Em casos graves, o ESTABELECIMENTO poderá cancelar definitivamente o contrato com aviso de 30 dias."),

    (7, "7. AUTORIZAÇÃO DE IMAGEM",
     "O CLIENTE autoriza, de forma gratuita e por prazo indeterminado, o uso de sua imagem, nome, resultados e "
     "estatísticas de partidas captados nas dependências do ESTABELECIMENTO, exclusivamente para fins de "
     "divulgação interna do ranking e promoção do ESTABELECIMENTO em seus canais de comunicação próprios, "
     "sem qualquer finalidade comercial com terceiros."),

    (8, "8. RESPONSABILIDADE POR DANOS",
     "O CLIENTE é integralmente responsável por qualquer dano causado às instalações, equipamentos, mobiliário "
     "ou demais bens do ESTABELECIMENTO durante a utilização do espaço. Em caso de dano comprovado, o CLIENTE "
     "será notificado e cobrado pelo valor correspondente ao reparo ou reposição do bem danificado. O "
     "ESTABELECIMENTO poderá suspender o acesso do CLIENTE até a regularização do débito."),

    (9, "9. CANCELAMENTO PELO ADMINISTRADOR",
     "9.1. O ESTABELECIMENTO poderá cancelar o contrato, a qualquer momento e sem necessidade de justificativa, "
     "mediante aviso-prévio de 30 (trinta) dias ao CLIENTE, com devolução integral do saldo proporcional "
     "restante das mensalidades já pagas.\n"
     "9.2. O cancelamento imediato, sem aviso-prévio e sem reembolso, poderá ocorrer nos casos de: "
     "(a) descumprimento grave das normas de conduta; (b) danos ao patrimônio não regularizados; "
     "(c) inadimplência superior a 30 (trinta) dias."),

    (10, "10. CANCELAMENTO PELO CLIENTE",
     "10.1. O CLIENTE poderá solicitar o cancelamento do contrato a qualquer momento.\n"
     "10.2. Para planos mensais: não há reembolso do mês em curso.\n"
     "10.3. Para planos trimestrais e anuais: será reembolsado o valor proporcional aos meses restantes, "
     "descontadas eventuais taxas administrativas.\n"
     "10.4. O pedido de cancelamento deverá ser formalizado com antecedência mínima de 5 (cinco) dias úteis "
     "pelos canais de atendimento do ESTABELECIMENTO."),

    (11, "11. PENALIDADES E SUSPENSÕES",
     "O ESTABELECIMENTO poderá aplicar as seguintes penalidades conforme a gravidade da infração:\n\n"
     "Advertência: Notificação formal por descumprimento leve das normas, sem interrupção do plano.\n\n"
     "Suspensão Temporária (3 a 7 dias): Aplicada em casos de atraso de pagamento entre 7 e 14 dias, "
     "cancelamento de horário fora do prazo ou comportamento inadequado moderado.\n\n"
     "Suspensão Temporária (8 a 30 dias): Aplicada em casos de reincidência, dano ao patrimônio não "
     "regularizado ou ofensas a outros jogadores ou funcionários.\n\n"
     "Cancelamento do Plano: Aplicado em casos de inadimplência superior a 30 dias, danos graves ao "
     "patrimônio, agressão física ou verbal grave ou segunda ocorrência de suspensão de longa duração."),

    (12, "12. LIMITE DE JOGADORES DO RANKING",
     "O ranking interno comporta no máximo 30 (trinta) jogadores ativos simultaneamente. Caso as vagas estejam "
     "preenchidas, o CLIENTE interessado poderá ingressar em lista de espera, sendo notificado "
     "automaticamente quando houver disponibilidade."),

    (13, "13. POLÍTICA DE CHUVAS",
     "13.1. Para jogadores do ranking: horários cancelados por chuva não serão reembolsados nem reagendados, "
     "pois o plano é uma mensalidade de acesso ao serviço.\n"
     "13.2. Para locações avulsas: em caso de chuva, o CLIENTE poderá reagendar o horário para outra data "
     "disponível, sem custo adicional, desde que o reagendamento seja solicitado com até 2 (duas) horas "
     "de antecedência do horário contratado."),

    (14, "14. USO DE ÁLCOOL E ALIMENTOS",
     "O consumo de bebidas alcoólicas e alimentos dentro do ESTABELECIMENTO é permitido exclusivamente na área "
     "reservada para este fim (bar e varanda). É expressamente proibido o consumo nas quadras e demais áreas "
     "esportivas. O descumprimento desta norma sujeita o CLIENTE às penalidades previstas no item 11."),

    (15, "15. ITENS PERDIDOS E SEGURANÇA",
     "O ESTABELECIMENTO não se responsabiliza por objetos, pertences, equipamentos esportivos ou quaisquer "
     "outros itens deixados, perdidos ou esquecidos nas dependências do clube, incluindo vestiários, quadras, "
     "áreas de convivência e estacionamento. Recomenda-se que o CLIENTE não deixe objetos de valor nas "
     "dependências do ESTABELECIMENTO."),

    (16, "16. FORO",
     "Fica eleito o foro da comarca onde o ESTABELECIMENTO está situado para dirimir quaisquer controvérsias "
     "oriundas deste contrato, com renúncia expressa a qualquer outro, por mais privilegiado que seja."),
]


def upgrade() -> None:
    op.create_table(
        "contrato_clausulas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_contrato_clausulas_ordem", "contrato_clausulas", ["ordem"])

    # Seed com as clausulas iniciais do contrato
    cc = sa.table(
        "contrato_clausulas",
        sa.column("ordem", sa.Integer),
        sa.column("titulo", sa.String),
        sa.column("texto", sa.Text),
        sa.column("ativo", sa.Boolean),
    )
    op.bulk_insert(cc, [
        {"ordem": o, "titulo": t, "texto": x, "ativo": True}
        for o, t, x in _CLAUSULAS
    ])


def downgrade() -> None:
    op.drop_index("ix_contrato_clausulas_ordem", table_name="contrato_clausulas")
    op.drop_table("contrato_clausulas")
