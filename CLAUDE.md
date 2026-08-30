# Roma Tênis — instruções para o Claude

Sistema de gestão de clube de tênis: ranking, agendamento e pagamentos.
FastAPI + PostgreSQL + frontend puro, em Docker Compose.

## 📖 Leia primeiro

**[`docs/SISTEMA.md`](docs/SISTEMA.md)** tem a referência completa: modelos,
regras de negócio, rotas, integrações e pendências. **Consulte antes de mexer em
regra de negócio** — as regras de agendamento, cota semanal, cancelamento e
cupons têm interações sutis que não são óbvias pelo código isolado.

## ⚠️ Deploy — a armadilha mais cara do projeto

O `Dockerfile` faz `COPY . .`: **o frontend é embutido na imagem**. Um
`docker compose build` comum reaproveita o cache e **não recopia os arquivos**.
O container segue servindo a versão antiga e parece que "o deploy não funcionou".

**Sempre use `--no-cache` e `--force-recreate`:**

```bash
cd /opt/romatenis && git pull && docker compose build --no-cache api && docker compose up -d --force-recreate api
```

Se o commit tiver migration, acrescente ao final:

```bash
&& docker compose exec -T api alembic upgrade head
```

Ao mexer no frontend, **suba o `CACHE_NAME`** em `frontend/service-worker.js` —
senão o PWA continua servindo o cache antigo mesmo após o deploy.

## Design

O app e o admin compartilham a mesma identidade: **Cinzel** nos títulos, **Inter**
no corpo, escala de superfícies (fundo → superfície → elevado) e espaçamento de
base 4px. Tokens em `frontend/css/style.css` (app) e no `<style>` de
`frontend/admin/index.html`. Detalhes na seção 16 de `docs/SISTEMA.md`.

Ao mexer em CSS: **confira os seletores contra o DOM real** (`querySelectorAll`)
antes de dar por pronto — regra com seletor errado é válida e silenciosa. E fure
o cache ao verificar, senão você avalia a versão antiga.

Duas armadilhas de espaçamento já custaram caro (seção 16.5 de `docs/SISTEMA.md`):

- A folga da barra fixa sai de `--folga-nav`. **Nunca** redeclare o `padding` do
  `main` com o atalho `padding:` sem repetir o token — o atalho zera a folga e o
  fim da página fica sob a navegação, inalcançável.
- **Não zere margem com `:last-child`** em cards. Quase todo card vive dentro de
  um wrapper de passo (`#form-reserva`, `#loc-s3`…), então é sempre `:last-child`
  do wrapper — o reset cola as bordas quando dois wrappers aparecem juntos.

Ponto de retorno do design anterior: tag `pre-redesign-2026-08-30`.

## Convenções

- **Português** em código, comentários, commits e UI
- Fuso `America/Sao_Paulo`; banco em UTC, conversão na borda
- Migrations manuais e sequenciais (`alembic/versions/00NN_descricao.py`)
- `selectinload` para relações — lazy load quebra em async
- Dados do usuário passam por `esc()` / `escHtml()` antes de ir para `innerHTML`
- Enums do Postgres guardam o *value*; novo valor exige `ALTER TYPE ... ADD VALUE`

## Segurança

Credenciais (Asaas, Autentique, SMTP, senha do admin) ficam **apenas** no `.env`
do servidor. Nunca exibir, copiar ou registrar esses valores — nem em commits,
nem em documentação, nem na conversa.

## Ao concluir uma mudança

1. Atualize a seção correspondente em `docs/SISTEMA.md` (regra nova, modelo novo,
   migration, pendência resolvida)
2. Suba o `CACHE_NAME` se mexeu no frontend
3. Informe o comando de deploy correto para o caso (com ou sem migration)
