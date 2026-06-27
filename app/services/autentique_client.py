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
    """Remove formatação, garante prefixo 55 e adiciona + para E.164."""
    digits = re.sub(r"\D", "", telefone)
    if not digits.startswith("55"):
        digits = "55" + digits
    return "+" + digits


def _gerar_pdf(
    nome: str,
    email: str,
    cpf: str | None,
    data_str: str,
    clausulas: list[dict] | None = None,
) -> bytes:
    """Gera o Termo de Adesão em PDF e retorna os bytes.

    clausulas: lista de {"titulo": str, "texto": str} vindas do banco.
    Se None, usa cláusula mínima de fallback.
    """
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "ROMA TÊNIS - TERMO DE ADESÃO", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0, 6,
        "Rosangela Pioli Siufi 05405791814  |  CNPJ: 29.616.848/0001-21  |  Nome Fantasia: Roma Tênis",
        new_x="LMARGIN", new_y="NEXT", align="C",
    )
    pdf.ln(8)

    # Dados do contratado
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "DADOS DO CONTRATADO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(192, 98, 42)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)

    def row(label: str, valor: str) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, label + ":", new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, valor, new_x="LMARGIN", new_y="NEXT")

    row("Nome completo", nome)
    row("E-mail", email)
    row("CPF", cpf if cpf else "Não informado")
    row("Data de adesão", data_str)
    pdf.ln(6)

    # Cláusulas
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "TERMOS E CONDIÇÕES", new_x="LMARGIN", new_y="NEXT")
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)

    _clausulas = clausulas if clausulas else [
        {"titulo": "1. Adesão",
         "texto": "O(a) cliente adere ao serviço de uso das instalações esportivas da Roma Tênis, "
                  "sujeitando-se ao regulamento interno vigente."},
    ]

    for c in _clausulas:
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(0, 5, c["titulo"])
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, c["texto"])
        pdf.ln(3)

    pdf.ln(8)

    # Rodapé de assinatura
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(
        0, 5,
        "Ao assinar este documento eletronicamente, o(a) CLIENTE declara ter lido, "
        "compreendido e aceito integralmente todos os termos acima.",
    )
    pdf.ln(10)
    pdf.line(20, pdf.get_y(), 100, pdf.get_y())
    pdf.ln(2)
    pdf.cell(80, 5, "Assinatura do(a) CLIENTE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.cell(0, 5, "Data/Hora da assinatura eletrônica: _________________________________",
             new_x="LMARGIN", new_y="NEXT")

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
        clausulas: list[dict] | None = None,
    ) -> tuple[str, str | None]:
        """
        Gera o PDF do contrato e cria o documento no Autentique via multipart upload.
        Retorna (document_id, link_assinatura).
        Lança AutentiqueError em caso de falha.
        """
        if not self._api_key:
            raise AutentiqueError("AUTENTIQUE_API_KEY não configurada")

        data_str = datetime.now(_FUSO_BR).strftime("%d/%m/%Y")
        pdf_bytes = _gerar_pdf(nome, email, cpf, data_str, clausulas)

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
                        "action": "SIGN",
                        **(
                            {
                                "phone": _normalizar_telefone(telefone),
                                "delivery_method": "DELIVERY_METHOD_WHATSAPP",
                            }
                            if telefone
                            else {"email": email}
                        ),
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

        logger.info("Autentique response status=%s body=%s", r.status_code, r.text[:800])

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
