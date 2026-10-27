FROM python:3.12-slim

WORKDIR /app

# Dependências de compilação para bcrypt e cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Remove ferramentas de build (binários já foram compilados)
RUN apt-get purge -y gcc libffi-dev python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# O processo roda sem root: um bug no servidor web não vira controle do
# container. A pasta de uploads é montada do host (docker-compose.yml) e
# precisa pertencer a este uid — ver o comando de deploy em docs/SISTEMA.md.
RUN useradd --system --uid 10001 --no-create-home roma \
    && mkdir -p /app/uploads \
    && chown -R roma:roma /app
USER roma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# 2 workers: suficiente para um clube pequeno; ajuste conforme uso real.
# --proxy-headers: o IP real do visitante vem do Caddy (X-Forwarded-For); sem
# isto todo acesso pareceria vir do proxy e o limite de tentativas por IP
# travaria todo mundo junto. Só o Caddy alcança esta porta, então confiar no
# cabeçalho é seguro.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
