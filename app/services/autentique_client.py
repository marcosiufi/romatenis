"""
Cliente para a API GraphQL do Autentique (contratos digitais).

Endpoint: https://api.autentique.com.br/v2/graphql
Auth:     Authorization: Bearer <AUTENTIQUE_API_KEY>

Fluxo:
  1. Gera PDF do Termo de Adesão com dados do jogador.
  2. Envia createDocument mutation com o PDF em base64 e o jogador como signatário.
  3. Retorna (document_id, link_assinatura).
  4. Webhook POST /api/v1/autentique/webhook marca contrato como assinado.
"""

import json
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fpdf import FPDF

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"
_FUSO_BR = ZoneInfo("America/Sao_Paulo")

# Autentique requer multipart upload (GraphQL multipart spec) — file: Upload!
_MUTATION = """
mutation CriarDocumento($file: Upload!, $document: DocumentInput!, $signers: [SignerInput!]!) {
  createDocument(file: $file, document: $document, signers: $signers) {
    id
    name
    signatures {
      public_id
      name
      email
      link {
        short_link
      }
    }
  }
}
"""


class AutentiqueError(Exception):
    pass


def _normalizar_telefone(telefone: str) -> str:
    """Remove formatação e garante prefixo 55 (Brasil)."""
    digits = re.sub(r"\D", "", telefone)
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


def _gerar_pdf(nome: str, email: str, cpf: str | None, data_str: str) -> bytes:
    """Gera o Termo de Adesão em PDF e retorna os bytes."""
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "ROMA TÊNIS - TERMO DE ADESÃO", ln=True, align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, "Associacao Roma Tenis  |  CNPJ: (a preencher)", ln=True, align="C")
    pdf.ln(8)

    # Dados do associado
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "DADOS DO ASSOCIADO", ln=True)
    pdf.set_draw_color(192, 98, 42)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)

    def row(label: str, valor: str) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, label + ":", ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, valor, ln=True)

    row("Nome completo", nome)
    row("E-mail", email)
    row("CPF", cpf if cpf else "Não informado")
    row("Data de adesão", data_str)
    pdf.ln(6)

    # Cláusulas
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "TERMOS E CONDIÇÕES", ln=True)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)

    clausulas = [
        ("1. Adesão",
         "O(a) associado(a) acima identificado(a) adere voluntariamente ao programa de ranking e "
         "agendamento de quadras da Roma Tênis, sujeitando-se ao regulamento interno vigente."),
        ("2. Mensalidade",
         "O(a) associado(a) compromete-se a manter o pagamento da mensalidade/plano escolhido em dia. "
         "A inadimplência por mais de 7 (sete) dias corridos resultará na suspensão do acesso ao ranking "
         "e à reserva de quadras."),
        ("3. Conduta",
         "O(a) associado(a) obriga-se a respeitar as normas de conduta do clube, os horários reservados "
         "e os demais usuários, sob pena de exclusão sem reembolso."),
        ("4. Imagem",
         "O(a) associado(a) autoriza a Roma Tênis a utilizar sua imagem, resultados e estatísticas de "
         "partidas exclusivamente para fins de divulgação do clube e do ranking interno, sem fins "
         "comerciais a terceiros."),
        ("5. Cancelamento",
         "O cancelamento da assinatura deverá ser solicitado com antecedência mínima de 30 (trinta) dias. "
         "Não há reembolso proporcional de valores já pagos, salvo em caso de encerramento das atividades "
         "pelo clube."),
        ("6. Foro",
         "Fica eleito o foro da comarca onde o clube está estabelecido para dirimir eventuais controvérsias "
         "decorrentes deste termo."),
    ]

    pdf.set_font("Helvetica", "", 9)
    for titulo, texto in clausulas:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, titulo, ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, texto)
        pdf.ln(2)

    pdf.ln(10)

    # Assinatura
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Ao assinar este documento eletronicamente, o(a) associado(a) declara ter lido,", ln=True)
    pdf.cell(0, 5, "compreendido e aceito todos os termos acima.", ln=True)
    pdf.ln(12)
    pdf.line(20, pdf.get_y(), 100, pdf.get_y())
    pdf.ln(2)
    pdf.cell(80, 5, "Assinatura do(a) Associado(a)", ln=True)
    pdf.ln(6)
    pdf.cell(0, 5, f"Data/Hora da assinatura eletrônica: _________________________________", ln=True)

    return bytes(pdf.output())


class AutentiqueClient:
    def __init__(self) -> None:
        self._api_key = settings.AUTENTIQUE_API_KEY

    async def enviar_contrato(
        self,
        nome: str,
        email: str,
        cpf: str | None = None,
        telefone: str | None = None,
    ) -> tuple[str, str | None]:
        """
        Gera o PDF do contrato e cria o documento no Autentique via multipart upload.
        Retorna (document_id, link_assinatura).
        Lança AutentiqueError em caso de falha.
        """
        if not self._api_key:
            raise AutentiqueError("AUTENTIQUE_API_KEY não configurada")

        data_str = datetime.now(_FUSO_BR).strftime("%d/%m/%Y")
        pdf_bytes = _gerar_pdf(nome, email, cpf, data_str)

        # GraphQL multipart request spec: file como Upload!
        operations = json.dumps({
            "query": _MUTATION,
            "variables": {
                "file": None,
                "document": {
                    "name": f"Termo de Adesao - {nome}",
                    "message": (
                        "Ola! Acesse o link abaixo para assinar seu Termo de Adesao da Roma Tenis "
                        "e ativar sua conta no ranking."
                    ),
                },
                "signers": [
                    {
                        "name": nome,
                        "email": email,
                        **({"phone": _normalizar_telefone(telefone)} if telefone else {}),
                        "action": "SIGN",
                    }
                ],
            },
        })

        multipart = {
            "operations": (None, operations, "application/json"),
            "map": (None, '{"0": ["variables.file"]}', "application/json"),
            "0": ("contrato.pdf", pdf_bytes, "application/pdf"),
        }

        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                _AUTENTIQUE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files=multipart,
            )

        if not r.is_success:
            raise AutentiqueError(f"Autentique HTTP {r.status_code}: {r.text[:300]}")

        body = r.json()
        errors = body.get("errors")
        if errors:
            raise AutentiqueError(f"Autentique GraphQL: {errors}")

        doc = body.get("data", {}).get("createDocument", {})
        doc_id = doc.get("id")
        if not doc_id:
            raise AutentiqueError(f"Autentique: documento sem ID na resposta: {body}")

        # Pega o link de assinatura do primeiro signatário
        link = None
        sigs = doc.get("signatures") or []
        if sigs:
            link = (sigs[0].get("link") or {}).get("short_link")

        logger.info("Contrato Autentique criado: doc_id=%s signer=%s", doc_id, email)
        return doc_id, link
