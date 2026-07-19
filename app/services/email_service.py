"""Serviço de e-mail via SMTP (usa smtplib nativo com run_in_executor)."""

import asyncio
import logging
import re
import smtplib
from html import unescape
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from functools import partial

from app.core.config import settings

logger = logging.getLogger(__name__)


def _html_base(titulo: str, corpo: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0ebe4;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr><td style="background:#1a3320;border-radius:12px 12px 0 0;padding:24px 32px;text-align:center">
          <h1 style="color:#c0622a;margin:0;font-size:1.4rem">🎾 Roma Tênis</h1>
          <p style="color:rgba(240,235,228,0.7);margin:6px 0 0;font-size:0.85rem">{titulo}</p>
        </td></tr>
        <tr><td style="background:#ffffff;padding:32px;border-radius:0 0 12px 12px">
          {corpo}
        </td></tr>
        <tr><td style="padding:16px;text-align:center;font-size:0.75rem;color:#888">
          {settings.SMTP_FROM_NAME} · Em caso de dúvida, basta responder este e-mail.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _btn(texto: str, link: str) -> str:
    return (
        f'<a href="{link}" style="display:inline-block;background:#c0622a;color:#fff;'
        f'padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;'
        f'font-size:0.9rem;margin:20px 0">{texto}</a>'
    )


def _fmt_whatsapp(numero: str) -> str:
    """'16991828504' → '(16) 99182-8504'. Aceita com ou sem DDI 55."""
    d = "".join(c for c in numero if c.isdigit())
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return ""


class EmailNaoConfigurado(RuntimeError):
    """SMTP_HOST/SMTP_USER ausentes — nada é enviado."""


def explicar_erro_smtp(exc: Exception) -> str:
    """Traduz as falhas mais comuns em instruções acionáveis."""
    txt = str(exc).lower()

    if "application-specific password required" in txt or "534" in txt:
        return (
            "O Google exige uma Senha de App. Ative a verificação em duas etapas "
            "e gere uma senha em myaccount.google.com/apppasswords — a senha "
            "normal da conta não funciona."
        )
    if "username and password not accepted" in txt or "535" in txt:
        return (
            "Usuário ou senha recusados. Confirme que SMTP_PASS é uma Senha de App "
            "de 16 caracteres (sem espaços) e que SMTP_USER é o endereço completo. "
            "No Google Workspace, o administrador também precisa manter o acesso "
            "SMTP habilitado."
        )
    if "not authorized" in txt or "550" in txt or "553" in txt:
        return (
            "O servidor recusou o remetente. O endereço em SMTP_FROM precisa ser "
            "a própria conta autenticada ou um alias autorizado nela."
        )
    if "timed out" in txt or "timeout" in txt:
        return (
            "Tempo esgotado ao conectar. Verifique se o servidor libera a porta de "
            "saída configurada (587 ou 465)."
        )
    if "connection refused" in txt or "getaddrinfo" in txt or "name or service" in txt:
        return "Não foi possível conectar ao servidor SMTP. Confira SMTP_HOST e SMTP_PORT."
    if "wrong version number" in txt or "ssl" in txt:
        return (
            "Incompatibilidade de criptografia: use porta 587 (STARTTLS) ou "
            "465 (SSL) conforme o provedor."
        )
    return f"{type(exc).__name__}: {exc}"


def remetente() -> str:
    """Endereço que aparece como remetente (From)."""
    return settings.SMTP_FROM.strip() or settings.SMTP_USER


def html_para_texto(html: str) -> str:
    """
    Versão em texto puro do e-mail.

    Um multipart/alternative sem a parte text/plain é lido pelos filtros como
    estrutura malformada e pesa contra a entrega na caixa de entrada.
    """
    txt = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html)
    # Preserva o destino dos links: "texto (url)"
    txt = re.sub(
        r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f"{re.sub(r'<[^>]+>', '', m.group(2)).strip()} ({m.group(1)})",
        txt,
    )
    txt = re.sub(r"(?i)<br\s*/?>", "\n", txt)
    txt = re.sub(r"(?i)</(p|div|tr|h[1-6]|li)>", "\n", txt)
    txt = re.sub(r"(?i)</t[dh]>", " ", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = unescape(txt)
    txt = re.sub(r"[ \t ]+", " ", txt)
    txt = re.sub(r" *\n *", "\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _send_sync(to_email: str, subject: str, html: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        raise EmailNaoConfigurado(
            "SMTP_HOST e SMTP_USER precisam estar definidos no .env do servidor."
        )

    de = remetente()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    # formataddr codifica só o nome; sem isso o acento de "Roma Tênis" faz o
    # Python codificar o header inteiro e o endereço vira ilegível para o SMTP.
    msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME, "utf-8")), de))
    msg["To"] = to_email
    # Respostas voltam para o remetente exibido, não para a conta de autenticação
    msg["Reply-To"] = de
    # A ordem importa: em multipart/alternative o cliente exibe a última parte
    # que souber renderizar, então o HTML vem depois do texto.
    msg.attach(MIMEText(html_para_texto(html), "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    porta = settings.SMTP_PORT
    if porta == 465:
        smtp_cm = smtplib.SMTP_SSL(settings.SMTP_HOST, porta, timeout=20)
    else:
        smtp_cm = smtplib.SMTP(settings.SMTP_HOST, porta, timeout=20)

    with smtp_cm as s:
        s.ehlo()
        if porta != 465:
            s.starttls()
            s.ehlo()
        if settings.SMTP_PASS:
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        # envelope-from = conta autenticada; o From exibido pode ser um alias
        s.sendmail(settings.SMTP_USER, to_email, msg.as_string())
    logger.info("E-mail enviado para %s — %s", to_email, subject)


def _send_sync_silencioso(to_email: str, subject: str, html: str) -> None:
    """Usado nos disparos automáticos: registra a falha sem derrubar o fluxo."""
    try:
        _send_sync(to_email, subject, html)
    except Exception as exc:
        logger.error("Falha ao enviar e-mail para %s: %s", to_email, exc)


async def send_email(to_email: str, subject: str, html: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, partial(_send_sync_silencioso, to_email, subject, html)
    )


async def send_email_estrito(to_email: str, subject: str, html: str) -> None:
    """Igual a send_email, mas propaga o erro — para o teste do painel."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(_send_sync, to_email, subject, html))


# ── Templates ─────────────────────────────────────────────────────────────────

async def enviar_boas_vindas(nome: str, email: str, link_app: str) -> None:
    """Enviado no cadastro, antes de qualquer contratação."""
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>! 👋</p>
    <p style="color:#555;line-height:1.6">
      Que bom ter você por aqui. Sua conta no <strong>Roma Tênis</strong> foi criada
      com sucesso — já dá para entrar no app e explorar.
    </p>
    <p style="text-align:center">{_btn("Acessar o app", link_app)}</p>
    <div style="background:#f7f3ee;border-radius:6px;padding:16px 20px;margin:20px 0">
      <p style="color:#333;margin:0 0 10px;font-weight:700;font-size:.92rem">O que você encontra por lá</p>
      <p style="color:#555;margin:0;line-height:1.8;font-size:.9rem">
        🏆 Classificação e pontuação da temporada<br>
        📅 Agendamento das suas partidas do ranking<br>
        🎾 Aluguel de quadra avulso<br>
        📊 Seu histórico de jogos e evolução
      </p>
    </div>
    <p style="color:#888;font-size:.85rem;line-height:1.6">
      Dúvidas? É só responder este e-mail ou chamar a gente no WhatsApp.
    </p>"""
    await send_email(
        email,
        "🎾 Bem-vindo ao Roma Tênis!",
        _html_base("Sua conta foi criada", corpo),
    )


async def enviar_abertura_inscricoes(nome: str, email: str, link: str) -> None:
    """Avisa quem está na lista de espera que as contratações abriram."""
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <div style="background:#eaf7ee;border-left:4px solid #4ab870;padding:16px 20px;margin:18px 0;border-radius:4px">
      <p style="color:#1e7a3e;margin:0;line-height:1.6;font-size:1rem">
        🎉 <strong>As inscrições do ranking estão abertas!</strong>
      </p>
    </div>
    <p style="color:#555;line-height:1.6">
      Você estava na nossa lista de espera e agora já pode escolher seu plano e
      garantir sua vaga no Programa de Ranking Roma Tênis.
    </p>
    <p style="text-align:center">{_btn("Ver planos e contratar", link)}</p>
    <p style="color:#888;font-size:.85rem;line-height:1.6">
      As vagas são limitadas e preenchidas por ordem de contratação — vale não deixar para depois.
    </p>"""
    await send_email(
        email,
        "🎉 As inscrições do ranking abriram — Roma Tênis",
        _html_base("Inscrições abertas", corpo),
    )


async def enviar_lembrete_partida(
    nome: str, email: str, quando: str, adversarios: str, tipo: str,
) -> None:
    """Lembrete algumas horas antes da partida agendada."""
    adv = (
        f'<tr><td><strong>Contra</strong></td><td>{adversarios}</td></tr>'
        if adversarios else ""
    )
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
      Passando para lembrar da sua partida de hoje. 🎾
    </p>
    <div style="background:#f7f3ee;border-left:4px solid #c0622a;padding:16px 20px;margin:18px 0;border-radius:4px">
      <table cellpadding="5" style="font-size:.95rem;color:#555;border-collapse:collapse">
        <tr><td><strong>Horário</strong></td><td>{quando}</td></tr>
        <tr><td><strong>Modalidade</strong></td><td>{tipo}</td></tr>
        {adv}
      </table>
    </div>
    <p style="color:#888;font-size:.85rem;line-height:1.6">
      Não vai conseguir ir? Cancele pelo app o quanto antes para liberar o horário
      para outros jogadores.
    </p>"""
    await send_email(
        email,
        f"🎾 Sua partida é hoje às {quando}",
        _html_base("Lembrete de partida", corpo),
    )

async def enviar_aviso_vencimento(nome: str, email: str, plano: str, dias: int, data_exp: str, link_renovacao: str) -> None:
    urgencia = "⚠️ HOJE" if dias <= 1 else f"em {dias} dias"
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">Sua assinatura <strong>{plano}</strong> do Roma Tênis vence
    <strong style="color:#c0622a">{urgencia}</strong> ({data_exp}).</p>
    <p style="color:#555;line-height:1.6">Renove agora para continuar jogando sem interrupções.</p>
    {_btn("Renovar Assinatura", link_renovacao)}
    <p style="color:#888;font-size:0.8rem;margin-top:16px">
      Acesse o app e vá em <strong>Perfil → Renovar</strong>.
    </p>"""
    await send_email(
        email,
        f"🎾 Sua assinatura Roma Tênis vence {urgencia}",
        _html_base("Aviso de Vencimento", corpo),
    )


async def enviar_confirmacao_pagamento(nome: str, email: str, plano: str, data_exp: str) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">✅ Pagamento confirmado! Sua assinatura <strong>{plano}</strong>
    está <strong style="color:#27ae60">ativa</strong> até <strong>{data_exp}</strong>.</p>
    <p style="color:#555;line-height:1.6">Bons jogos! 🎾</p>"""
    await send_email(
        email,
        "✅ Pagamento confirmado — Roma Tênis",
        _html_base("Pagamento Confirmado", corpo),
    )


async def enviar_contrato_pendente(nome: str, email: str, whatsapp: str = "") -> None:
    """
    Lembrete de contrato pendente.

    A assinatura acontece pelo link que a Autentique envia por WhatsApp — este
    e-mail apenas avisa e direciona para lá, sem link próprio de assinatura.
    """
    fmt = _fmt_whatsapp(whatsapp)
    numero = (
        f'<p style="color:#555;line-height:1.6;margin-top:.5rem">'
        f'Enviamos para o WhatsApp <strong>{fmt}</strong>.</p>'
    ) if fmt else ""

    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
      Seu <strong>Termo de Adesão</strong> ainda está aguardando assinatura.
    </p>
    <div style="background:#f7f3ee;border-left:4px solid #c0622a;padding:14px 18px;margin:20px 0;border-radius:4px">
      <p style="color:#333;margin:0;line-height:1.6">
        📲 <strong>O contrato foi enviado pelo WhatsApp</strong>, pela plataforma Autentique.
        Para assinar, abra a conversa no WhatsApp e siga o link enviado por lá.
      </p>
      {numero}
    </div>
    <div style="background:#fdf6e8;border:1px solid #e0a040;padding:14px 18px;margin:20px 0;border-radius:6px">
      <p style="color:#7a5a1e;margin:0;line-height:1.6;font-size:.92rem">
        ⚠️ <strong>Importante:</strong> enquanto o contrato não for assinado, você
        <strong>não consegue reservar horários nem participar das partidas do ranking</strong>,
        mesmo com o pagamento já confirmado.
      </p>
    </div>
    <p style="color:#888;font-size:.85rem;line-height:1.6">
      Não encontrou a mensagem? Verifique se o WhatsApp cadastrado está correto no
      seu perfil, ou entre em contato com a gente.
    </p>"""
    await send_email(
        email,
        "📄 Seu contrato está aguardando assinatura — Roma Tênis",
        _html_base("Contrato Pendente", corpo),
    )


async def alertar_admin_falha_contrato(
    admin_email: str, jogador_nome: str, jogador_email: str,
    jogador_telefone: str, erro: str,
) -> None:
    """
    Avisa o administrador que a Autentique não conseguiu enviar o contrato.

    Sem contrato o jogador fica pago porém bloqueado, e a falha é silenciosa —
    daí o alerta ativo em vez de só registrar no log.
    """
    tel = _fmt_whatsapp(jogador_telefone) or jogador_telefone or "—"
    corpo = f"""
    <p style="color:#333;font-size:1rem">Falha no envio automático de contrato</p>
    <div style="background:#fdeaea;border-left:4px solid #c0392b;padding:14px 18px;margin:18px 0;border-radius:4px">
      <p style="color:#7a1e1e;margin:0;line-height:1.6">
        O contrato de <strong>{jogador_nome}</strong> não pôde ser enviado pela Autentique.
        O jogador <strong>pagou mas está bloqueado</strong> até assinar.
      </p>
    </div>
    <table cellpadding="6" style="font-size:.9rem;color:#555;border-collapse:collapse">
      <tr><td><strong>Jogador</strong></td><td>{jogador_nome}</td></tr>
      <tr><td><strong>E-mail</strong></td><td>{jogador_email}</td></tr>
      <tr><td><strong>WhatsApp</strong></td><td>{tel}</td></tr>
      <tr><td><strong>Erro</strong></td><td style="color:#c0392b">{erro}</td></tr>
    </table>
    <p style="color:#555;line-height:1.6;margin-top:18px">
      <strong>O que fazer:</strong> abra o painel em <em>Jogadores</em>, localize o jogador
      e use <em>Enviar contrato</em> para tentar de novo. Se a Autentique seguir
      falhando, confirme a assinatura manualmente por lá.
    </p>"""
    await send_email(
        admin_email,
        f"🚨 Falha ao enviar contrato — {jogador_nome}",
        _html_base("Ação necessária", corpo),
    )


async def enviar_contrato_assinado(nome: str, email: str) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
      ✅ Seu Termo de Adesão foi assinado com sucesso. Sua conta no ranking Roma Tênis está ativa!
    </p>
    <p style="color:#555;line-height:1.6">Bons jogos! 🎾</p>"""
    await send_email(
        email,
        "✅ Contrato assinado — Roma Tênis",
        _html_base("Contrato Assinado", corpo),
    )


async def enviar_reset_senha(nome: str, email: str, link_reset: str) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">Recebemos uma solicitação para redefinir a senha da sua conta Roma Tênis.</p>
    {_btn("Redefinir minha senha", link_reset)}
    <p style="color:#888;font-size:0.8rem;margin-top:16px">
      Este link expira em <strong>1 hora</strong>. Se você não solicitou a redefinição, ignore este e-mail com segurança.
    </p>"""
    await send_email(
        email,
        "🔐 Redefinição de senha — Roma Tênis",
        _html_base("Redefinir Senha", corpo),
    )


async def enviar_convocacao_lista_espera(nome: str, email: str, horas: int, link: str) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
        Uma vaga no <strong>Programa de Ranking Roma Tênis</strong> acabou de abrir!
        Você está na fila de espera e foi convocado(a) para confirmar sua participação.
    </p>
    <p style="color:#555;line-height:1.6">
        Você tem <strong>{horas} horas</strong> para acessar o site e contratar seu plano.
        Caso não haja confirmação nesse prazo, a vaga passará ao próximo da lista.
    </p>
    {_btn("Garantir minha vaga", link)}
    <p style="color:#888;font-size:0.85rem;margin-top:1rem">
        Se não tiver mais interesse, ignore este e-mail.
    </p>"""
    await send_email(
        email,
        "🎾 Sua vaga no ranking está disponível! — Roma Tênis",
        _html_base("Vaga Disponível no Ranking", corpo),
    )


async def enviar_confirmacao_lista_espera(nome: str, email: str, posicao: int) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
        Você entrou na <strong>lista de espera</strong> do Programa de Ranking Roma Tênis.
        Sua posição atual é <strong>#  {posicao}</strong>.
    </p>
    <p style="color:#555;line-height:1.6">
        Você será notificado por e-mail quando uma vaga ficar disponível.
        Assim que for convocado(a), terá 48 horas para confirmar e contratar seu plano.
    </p>"""
    await send_email(
        email,
        "⏳ Você está na lista de espera — Roma Tênis",
        _html_base("Lista de Espera do Ranking", corpo),
    )


async def enviar_aviso_pausa(nome: str, email: str, data_retorno: str | None) -> None:
    retorno = f"com retorno previsto em <strong>{data_retorno}</strong>" if data_retorno else ""
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">Sua assinatura Roma Tênis foi <strong>pausada</strong> {retorno}.</p>
    <p style="color:#555;line-height:1.6">Quando estiver pronto para voltar, entre em contato ou acesse o app.</p>"""
    await send_email(
        email,
        "⏸ Assinatura pausada — Roma Tênis",
        _html_base("Assinatura Pausada", corpo),
    )
