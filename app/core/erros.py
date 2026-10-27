"""Tradução de erros do banco em respostas que o usuário entende."""
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

MSG_DUPLICADO = "E-mail, telefone ou CPF já cadastrado em outro jogador."


async def commit_ou_409(db: AsyncSession, mensagem: str = MSG_DUPLICADO) -> None:
    """Commit que vira 409 quando esbarra num campo único (e-mail, telefone, CPF).

    Sem isto a violação chegava ao usuário como erro 500, sem explicação, e
    ficava no log como falha do servidor.
    """
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=mensagem) from exc
