"""Validadores de documentos brasileiros."""


def limpar_cpf(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


def cpf_valido(cpf: str) -> bool:
    """Valida um CPF pelos dois dígitos verificadores."""
    cpf = limpar_cpf(cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False

    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(cpf[tamanho]):
            return False
    return True
