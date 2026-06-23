import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin, get_current_player, hash_password
from app.core.database import get_db
from app.models.player import Player, StatusJogador
from app.schemas.player import PlayerCreate, PlayerOut, PlayerUpdate

_UPLOAD_DIR = "/app/uploads/avatars"
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerOut])
async def list_players(
    db: Annotated[AsyncSession, Depends(get_db)],
    apenas_ativos: bool = False,
):
    """Ranking público — ordenado por pontos da temporada.

    apenas_ativos=true: só retorna ATIVO (usado para seleção de convites).
    Padrão: ATIVO + INATIVO dentro de 7 dias (aparecem com badge no ranking).
    """
    sete_dias_atras = datetime.now(timezone.utc) - timedelta(days=7)
    if apenas_ativos:
        cond = Player.status == StatusJogador.ATIVO.value
    else:
        cond = or_(
            Player.status == StatusJogador.ATIVO.value,
            and_(
                Player.status == StatusJogador.INATIVO.value,
                Player.data_inativacao >= sete_dias_atras,
            ),
        )
    result = await db.execute(
        select(Player).where(cond).order_by(Player.pontos_ranking_temporada_atual.desc())
    )
    return result.scalars().all()


@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def create_player(
    body: PlayerCreate,
    _admin: Annotated[Player, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin cria um jogador."""
    exists = await db.execute(select(Player).where(Player.email == body.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")

    player = Player(
        nome=body.nome,
        telefone=body.telefone,
        email=body.email,
        senha_hash=hash_password(body.senha),
        cpf=body.cpf,
        data_nascimento=body.data_nascimento,
        apelido=body.apelido,
        rua=body.rua,
        numero=body.numero,
        complemento=body.complemento,
        bairro=body.bairro,
        cidade=body.cidade,
        estado=body.estado,
        pais=body.pais or "Brasil",
        cep=body.cep,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/me", response_model=PlayerOut)
async def get_me(player: Annotated[Player, Depends(get_current_player)]):
    return player


@router.put("/me/foto", response_model=PlayerOut)
async def upload_foto(
    foto: Annotated[UploadFile, File(...)],
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ext = os.path.splitext(foto.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato inválido. Use JPG, PNG ou WebP.",
        )
    content = await foto.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo muito grande. Máximo 5 MB.",
        )
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    filename = f"{player.id}{ext}"
    with open(os.path.join(_UPLOAD_DIR, filename), "wb") as f:
        f.write(content)
    player.foto_url = f"/uploads/avatars/{filename}"
    await db.commit()
    await db.refresh(player)
    return player


@router.patch("/me", response_model=PlayerOut)
async def update_me(
    body: PlayerUpdate,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(
    player_id: int,
    _current: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")
    return player


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: int,
    body: PlayerUpdate,
    _admin: Annotated[Player, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin atualiza qualquer jogador."""
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player
