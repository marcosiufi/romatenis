from fastapi import APIRouter, Depends

from app.core.auth import get_current_player
from app.core.database import get_db
from app.models.player import Player
from app.schemas.cupom import CupomValidarIn, CupomValidarOut
from app.services import cupom_service

router = APIRouter(prefix="/cupons", tags=["cupons"])


@router.post("/validar", response_model=CupomValidarOut)
async def validar(
    body: CupomValidarIn,
    _player: Player = Depends(get_current_player),
    db=Depends(get_db),
):
    """Confere um cupom e devolve o percentual, para o front prever o desconto."""
    try:
        cupom = await cupom_service.validar_cupom(db, body.codigo)
    except cupom_service.CupomError as e:
        return CupomValidarOut(valido=False, msg=str(e))
    return CupomValidarOut(
        valido=True,
        codigo=cupom.codigo,
        percentual=cupom.percentual,
        descricao=cupom.descricao,
        msg=f"Cupom aplicado: {cupom.percentual}% de desconto.",
    )
