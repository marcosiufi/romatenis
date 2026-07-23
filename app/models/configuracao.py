from sqlalchemy import Boolean, Integer, Numeric, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Configuracao(Base):
    __tablename__ = "configuracoes"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Preços totais por plano (R$)
    preco_mensal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=89.90)
    preco_trimestral: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=239.90)
    preco_semestral: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=449.90)
    preco_anual: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=839.90)

    # Locação avulsa
    preco_locacao_hora: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=120.00)

    # Jogo avulso — cobrado por convidado de fora do ranking
    preco_jogo_avulso: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=60.00)

    # Horário de funcionamento global — LEGADO, substituído por HorarioDiaSemana
    # (um registro por dia, semeado para os 7 dias na migration 0021) e por
    # HorarioEspecial (por data). Restam apenas como fallback defensivo em
    # public.py, inalcançável enquanto os 7 dias existirem. Não editável pelo
    # admin: o painel usa a tela "Horários por dia da semana".
    hora_abertura: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    hora_fechamento: Mapped[int] = mapped_column(Integer, nullable=False, default=22)

    # Limite de jogadores no ranking
    limite_ranking: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # ── Disponibilidade comercial ────────────────────────────────────────────
    # Permitem divulgar antes da abertura: com estes desligados o cadastro e a
    # lista de espera continuam funcionando, mas ninguém contrata nem reserva.
    contratacao_planos_ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    reservas_ativas: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    msg_planos_desabilitado: Mapped[str] = mapped_column(
        Text, nullable=False,
        default="Ainda não estamos aceitando contratações. Cadastre-se e entre "
                "na lista de espera para ser avisado assim que abrirmos!",
    )
    msg_reservas_desabilitado: Mapped[str] = mapped_column(
        Text, nullable=False,
        default="Ainda não estamos aceitando reservas de quadra. "
                "Em breve liberaremos os agendamentos!",
    )

    # ── Regras de antecedência (horas) ───────────────────────────────────────
    # Ranking: reserva normal exige no mínimo X h; abaixo da janela de última
    # hora libera qualquer slot; entre as duas fica bloqueado.
    ranking_antecedencia_minima_horas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default="6"
    )
    ranking_ultima_hora_horas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Jogo avulso: só pode ser reservado dentro desta janela antes do início.
    jogo_avulso_ultima_hora_horas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Locação avulsa: slot reservado ao ranking só é liberado para locação
    # quando faltar menos que este tempo para o jogo.
    locacao_libera_slot_ranking_horas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default="6"
    )
    # Cancelamento de jogos (ranking e avulso): cancelar com menos que este
    # tempo de antecedência abate o jogo do saldo semanal (conta como WO).
    cancelamento_antecedencia_horas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )

    # Dados da empresa
    razao_social: Mapped[str] = mapped_column(String(300), nullable=False, default="Rosangela Pioli Siufi")
    nome_fantasia: Mapped[str] = mapped_column(String(300), nullable=False, default="Roma Tênis")
    cnpj: Mapped[str] = mapped_column(String(30), nullable=False, default="29.616.848/0001-21")
    cpf_responsavel: Mapped[str] = mapped_column(String(20), nullable=False, default="05405791814")
    end_logradouro: Mapped[str] = mapped_column(String(300), nullable=False, default="Rua Minoru Mizutani")
    end_numero: Mapped[str] = mapped_column(String(20), nullable=False, default="99")
    end_complemento: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    end_bairro: Mapped[str] = mapped_column(String(200), nullable=False, default="Recreio das Acácias")
    end_cidade: Mapped[str] = mapped_column(String(200), nullable=False, default="Ribeirão Preto")
    end_estado: Mapped[str] = mapped_column(String(2), nullable=False, default="SP")
    end_pais: Mapped[str] = mapped_column(String(100), nullable=False, default="Brasil")
    end_cep: Mapped[str] = mapped_column(String(10), nullable=False, default="14098-555")
    whatsapp: Mapped[str] = mapped_column(String(30), nullable=False, default="5516993618092")
    instagram: Mapped[str] = mapped_column(String(100), nullable=False, default="romatenisrp")
    email_contato: Mapped[str] = mapped_column(String(200), nullable=False, default="contato@romatenis.com.br")

    @classmethod
    async def get(cls, db: AsyncSession) -> "Configuracao":
        """Retorna a única linha de config, criando com defaults se não existir."""
        row = (await db.execute(select(cls).where(cls.id == 1))).scalar_one_or_none()
        if row is None:
            row = cls(id=1)
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row
