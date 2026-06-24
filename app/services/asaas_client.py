"""
Cliente HTTP assíncrono para o gateway Asaas.

Sandbox:  https://sandbox.asaas.com/api/v3
Produção: https://api.asaas.com/api/v3
"""

import httpx

from app.core.config import settings

BILLING_TYPE_MAP: dict[str, str] = {
    "pix_avista": "PIX",
    "boleto_avista": "BOLETO",
    "cartao_parcelado": "CREDIT_CARD",
}


class AsaasError(Exception):
    pass


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.ASAAS_BASE_URL,
        headers={"access_token": settings.asaas_api_key, "Content-Type": "application/json"},
        timeout=15.0,
    )


class AsaasClient:
    async def get_or_create_customer(
        self,
        nome: str,
        email: str,
        telefone: str,
        cpf: str | None = None,
        data_nascimento: str | None = None,
    ) -> str:
        """Retorna o ID de cliente Asaas, criando-o se ainda não existir."""
        async with _cliente() as c:
            r = await c.get("/customers", params={"email": email})
            r.raise_for_status()
            data = r.json().get("data", [])
            if data:
                customer = data[0]
                # Atualiza CPF se ausente — exigido pelo Asaas para cobranças PIX
                if cpf and not customer.get("cpfCnpj"):
                    await c.put(
                        f"/customers/{customer['id']}",
                        json={"cpfCnpj": _limpar_cpf(cpf)},
                    )
                return customer["id"]

            payload: dict = {
                "name": nome,
                "email": email,
                "mobilePhone": _limpar_fone(telefone),
            }
            if cpf:
                payload["cpfCnpj"] = _limpar_cpf(cpf)
            if data_nascimento:
                payload["birthDate"] = data_nascimento

            r = await c.post("/customers", json=payload)
            if not r.is_success:
                raise AsaasError(f"Asaas /customers {r.status_code}: {r.text}")
            return r.json()["id"]

    async def criar_cobranca(
        self,
        customer_id: str,
        valor: float,
        billing_type: str,
        due_date: str,
        descricao: str,
        installment_count: int = 1,
    ) -> dict:
        payload: dict = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": round(valor, 2),
            "dueDate": due_date,
            "description": descricao,
        }
        if billing_type in ("CREDIT_CARD", "BOLETO") and installment_count > 1:
            payload["installmentCount"] = installment_count
            payload["installmentValue"] = round(valor / installment_count, 2)

        async with _cliente() as c:
            r = await c.post("/payments", json=payload)
            if not r.is_success:
                raise AsaasError(f"Asaas /payments {r.status_code}: {r.text}")
            return r.json()

    async def get_pix_qrcode(self, payment_id: str) -> dict:
        async with _cliente() as c:
            r = await c.get(f"/payments/{payment_id}/pixQrCode")
            r.raise_for_status()
            return r.json()

    async def get_cobranca(self, payment_id: str) -> dict:
        async with _cliente() as c:
            r = await c.get(f"/payments/{payment_id}")
            r.raise_for_status()
            return r.json()

    async def solicitar_antecipacao(self, payment_id: str) -> dict:
        async with _cliente() as c:
            r = await c.post("/anticipations", json={"payment": payment_id})
            if not r.is_success:
                raise AsaasError(f"Asaas /anticipations {r.status_code}: {r.text}")
            return r.json()


def _limpar_fone(telefone: str) -> str:
    return "".join(c for c in telefone if c.isdigit())


def _limpar_cpf(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())
