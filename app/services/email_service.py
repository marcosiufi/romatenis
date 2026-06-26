"""Serviço de e-mail via SMTP (usa smtplib nativo com run_in_executor)."""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
          Roma Tênis · Este é um e-mail automático, não responda.
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


def _send_sync(to_email: str, subject: str, html: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP não configurado — e-mail não enviado para %s", to_email)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Roma Tênis <{settings.SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.ehlo()
            if settings.SMTP_PORT != 465:
                s.starttls()
            if settings.SMTP_PASS:
                s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.sendmail(settings.SMTP_USER, to_email, msg.as_string())
        logger.info("E-mail enviado para %s — %s", to_email, subject)
    except Exception as exc:
        logger.error("Falha ao enviar e-mail para %s: %s", to_email, exc)


async def send_email(to_email: str, subject: str, html: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(_send_sync, to_email, subject, html))


# ── Templates ─────────────────────────────────────────────────────────────────

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


async def enviar_contrato_pendente(nome: str, email: str, link_assinatura: str) -> None:
    corpo = f"""
    <p style="color:#333;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
    <p style="color:#555;line-height:1.6">
      Para ativar sua conta no ranking Roma Tênis, assine o Termo de Adesão clicando no botão abaixo.
    </p>
    <p style="text-align:center;margin:1.5rem 0">
      <a href="{link_assinatura}" style="background:#c0622a;color:#fff;padding:.7rem 1.5rem;border-radius:6px;text-decoration:none;font-weight:700">
        Assinar Contrato
      </a>
    </p>
    <p style="color:#888;font-size:.85rem">
      O link acima é de uso exclusivo e pessoal. Não compartilhe com terceiros.
    </p>"""
    await send_email(
        email,
        "📄 Assine seu Termo de Adesão — Roma Tênis",
        _html_base("Assine seu Contrato", corpo),
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
