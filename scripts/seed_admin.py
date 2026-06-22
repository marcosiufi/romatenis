"""
Cria o primeiro usuário admin no banco.
Uso: python scripts/seed_admin.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from app.core.auth import hash_password
from app.core.database import AsyncSessionLocal
from app.models.player import Player


async def main() -> None:
    email = input("E-mail do admin: ").strip()
    nome = input("Nome: ").strip()
    telefone = input("Telefone (WhatsApp, com DDD): ").strip()
    senha = input("Senha: ").strip()

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Player).where(Player.email == email))
        if existing.scalar_one_or_none():
            print("Jogador com esse e-mail já existe.")
            return

        admin = Player(
            nome=nome,
            telefone=telefone,
            email=email,
            senha_hash=hash_password(senha),
            is_admin=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Admin '{nome}' criado com sucesso (id={admin.id}).")


if __name__ == "__main__":
    asyncio.run(main())
