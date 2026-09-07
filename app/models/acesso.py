"""Controle de acesso à quadra — leitores faciais Intelbras.

Arquitetura: o servidor **não** fala com os leitores. Eles ficam na rede local
da quadra (IP 192.168.x.x) e a VPS está na nuvem — não há rota entre os dois, e
expor um controlador de acesso na internet seria imprudente. Quem conversa com
os leitores é o agente que roda na quadra (`agente-acesso/`): ele busca o estado
desejado aqui, aplica nos leitores pela rede local e devolve os eventos.

O servidor é a fonte da verdade do *estado desejado*; o agente reconcilia. Isso
faz o sistema se curar sozinho: se o agente ficar offline, ao voltar ele compara
tudo de novo e corrige. E se a internet cair no meio de um jogo, quem já foi
liberado no leitor continua entrando.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ENUM as pg_enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PapelDispositivo(str, enum.Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class StatusCredencial(str, enum.Enum):
    PENDENTE_FOTO = "pendente_foto"     # pessoa ainda não enviou a selfie
    PENDENTE_ENVIO = "pendente_envio"   # foto pronta, aguardando o agente
    SINCRONIZADA = "sincronizada"       # cadastrada nos leitores
    ERRO = "erro"                       # o leitor recusou (rosto ilegível, etc.)
    REMOVIDA = "removida"               # apagada dos leitores


class StatusJanela(str, enum.Enum):
    ATIVA = "ativa"
    CANCELADA = "cancelada"


class TipoEventoAcesso(str, enum.Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    NEGADO = "negado"
    ABERTURA_REMOTA = "abertura_remota"


class StatusComando(str, enum.Enum):
    PENDENTE = "pendente"
    EXECUTADO = "executado"
    ERRO = "erro"


class DispositivoAcesso(Base):
    """Um leitor facial. Dois no projeto: um de entrada, um de saída.

    Host, usuário e senha são cadastrados no painel do admin e servidos ao
    agente; a senha fica cifrada (ver `app.core.cripto`).
    """
    __tablename__ = "dispositivos_acesso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    papel: Mapped[PapelDispositivo] = mapped_column(
        pg_enum(PapelDispositivo, name="papel_dispositivo"), nullable=False
    )
    modelo: Mapped[str] = mapped_column(String(60), nullable=False, default="SS 3531 MF LITE")

    host: Mapped[str] = mapped_column(String(120), nullable=False)
    porta: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    usuario: Mapped[str] = mapped_column(String(80), nullable=False, default="admin")
    senha_cifrada: Mapped[str] = mapped_column(Text, nullable=False, default="")

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Preenchidos pelo agente a cada ciclo — é o que o painel mostra como saúde.
    ultimo_contato_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CredencialAcesso(Base):
    """Identidade única de quem pode passar pelo portão.

    Aponta para exatamente uma das três origens de pessoa que o sistema tem:
    associado do ranking, convidado de jogo avulso, ou cliente de locação
    avulsa (que não tem conta, então se prende à reserva).
    """
    __tablename__ = "credenciais_acesso"
    __table_args__ = (
        CheckConstraint(
            "(player_id IS NOT NULL)::int + (convidado_id IS NOT NULL)::int "
            "+ (booking_id IS NOT NULL)::int = 1",
            name="ck_credencial_uma_origem",
        ),
        Index("ix_credenciais_acesso_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    convidado_id: Mapped[int | None] = mapped_column(
        ForeignKey("convidados.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, unique=True
    )

    # Nome desnormalizado: é o que aparece na tela do leitor e no log de eventos,
    # e precisa sobreviver mesmo se a origem for apagada.
    nome: Mapped[str] = mapped_column(String(150), nullable=False)

    # Identificador do usuário dentro do leitor. Estável e legível ("RT000123"),
    # para dar para achar a pessoa na tela do equipamento quando algo der errado.
    id_dispositivo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # sha256 do arquivo efetivamente enviado ao leitor. É como o agente sabe que
    # a pessoa trocou a selfie e precisa reenviar — comparar URL não bastaria,
    # porque o upload sobrescreve o arquivo mantendo o nome.
    foto_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Convidado e cliente de locação não têm login, mas precisam mandar a
    # selfie. Este token vira um link de uso único enviado por WhatsApp/e-mail.
    token_selfie: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    status: Mapped[StatusCredencial] = mapped_column(
        pg_enum(StatusCredencial, name="status_credencial"),
        nullable=False, default=StatusCredencial.PENDENTE_FOTO,
    )
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    sincronizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    player = relationship("Player")
    convidado = relationship("Convidado")
    booking = relationship("Booking")
    janelas: Mapped[list["JanelaAcesso"]] = relationship(
        back_populates="credencial", cascade="all, delete-orphan"
    )


class JanelaAcesso(Base):
    """Intervalo em que uma credencial pode passar pelo portão.

    Sai da reserva mais as folgas configuráveis: `inicio` é o começo da reserva
    menos `acesso_minutos_antes`, `fim` é o término mais `acesso_minutos_depois`
    (que existe para a pessoa conseguir sair pelo leitor de saída).

    Uma pessoa pode ter várias janelas ao mesmo tempo (vários jogos na semana),
    e por isso o leitor não guarda a janela: o agente habilita e desabilita a
    credencial conforme o relógio. Ver `agente-acesso/`.
    """
    __tablename__ = "janelas_acesso"
    __table_args__ = (
        Index("ix_janelas_acesso_periodo", "inicio", "fim"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    credencial_id: Mapped[int] = mapped_column(
        ForeignKey("credenciais_acesso.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )

    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[StatusJanela] = mapped_column(
        pg_enum(StatusJanela, name="status_janela"), nullable=False, default=StatusJanela.ATIVA
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    credencial: Mapped["CredencialAcesso"] = relationship(back_populates="janelas")
    booking = relationship("Booking")


class EventoAcesso(Base):
    """Passagem registrada por um leitor, empurrada pelo agente.

    `credencial_id` é opcional de propósito: o leitor também registra tentativas
    de quem não está cadastrado, e esse é justamente o evento que interessa
    investigar.
    """
    __tablename__ = "eventos_acesso"
    __table_args__ = (
        Index("ix_eventos_acesso_momento", "momento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    dispositivo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dispositivos_acesso.id", ondelete="SET NULL"), nullable=True
    )
    credencial_id: Mapped[int | None] = mapped_column(
        ForeignKey("credenciais_acesso.id", ondelete="SET NULL"), nullable=True, index=True
    )

    tipo: Mapped[TipoEventoAcesso] = mapped_column(
        pg_enum(TipoEventoAcesso, name="tipo_evento_acesso"), nullable=False
    )
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Como o leitor identificou a pessoa, mesmo sem credencial nossa.
    nome_lido: Mapped[str | None] = mapped_column(String(150), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Chave que o agente gera a partir do registro do leitor. Evita duplicar o
    # mesmo evento quando o agente reenvia um lote por falha de rede.
    chave_externa: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    recebido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dispositivo = relationship("DispositivoAcesso")
    credencial = relationship("CredencialAcesso")


class ComandoAcesso(Base):
    """Ação pontual para o agente executar — o que não cabe na reconciliação.

    Hoje: abrir o portão remotamente pelo painel e forçar o reenvio de uma foto.
    A fila existe porque o servidor não alcança o agente: ele é quem busca.
    """
    __tablename__ = "comandos_acesso"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[StatusComando] = mapped_column(
        pg_enum(StatusComando, name="status_comando_acesso"),
        nullable=False, default=StatusComando.PENDENTE, index=True,
    )
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    executado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
