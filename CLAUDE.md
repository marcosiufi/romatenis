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

**Leia [`docs/DESIGN.md`](docs/DESIGN.md) antes de mexer em tela.** O sistema
segue a gramática da Apple traduzida para a web, com as cores da marca: o app
fala **iOS** (texto de 17px, alvo de 44px, título grande que encolhe, listas
agrupadas, folhas que sobem do pé da tela) e o admin fala **macOS** (13px,
controles de 32px, barra lateral, barra de ferramentas presa). Fonte do sistema
(SF Pro no aparelho Apple, Inter de `/fonts` no resto); Cinzel só nas letras do
logotipo. Tokens com nome de papel (`--plano`, `--superficie`, `--tinta`,
`--tint`) em `frontend/css/style.css` (app) e no `<style>` de
`frontend/admin/index.html`. Histórico na seção 20 de `docs/SISTEMA.md`.

Nada de `confirm()`/`alert()`: use `confirmar()` e `alertar()` (existem nos dois
JS). Texto de interface em caixa de frase, sem emoji, sem "(s)" para plural, sem
`opacity` para esmaecer texto (use `--tinta-2`/`--tinta-3`).

**App e admin têm tema claro e escuro** (seções 17 e 18), com a mesma mecânica e
a mesma paleta: `localStorage.tema` guarda `auto` | `claro` | `escuro`, e o CSS lê
`data-tema` no `<html>` — no automático o atributo é removido e
`prefers-color-scheme` decide. O módulo é um `<script>` inline no `<head>`;
movê-lo para o JS do fim do `<body>` faz a página piscar no tema errado. O
usuário troca no cartão Aparência (Perfil, no app) ou no rodapé da barra lateral
(admin).

Ao acrescentar cor, **use os tokens** — cor fixa no `style` inline quebra um dos
dois temas, e foi o erro mais comum encontrado nas duas telas. Para tinta sobre
fundo tingido use `color-mix`, não um `rgba` fixo. Se mudar um token de cor,
mude nos **dois** arquivos (`frontend/css/style.css` e o `<style>` do admin).
Os nomes antigos (`--clr-*`, `--cor-*`) seguem como aliases e não devem ser
removidos. A landing tem tokens próprios e continua só no escuro.

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

## Testar na máquina local

Antes de publicar, rode tudo localmente com `docker-compose.local.yml` (porta
**8100** — a 8000 é de outro projeto). Passo a passo e logins de teste em
[`docs/LOCAL.md`](docs/LOCAL.md); o código entra por volume, então o frontend
atualiza com F5. Mudanças de design só vão para `main` depois do Marco testar.

## Controle de acesso (portão da quadra)

Leitores faciais Intelbras na rede local; a VPS **não** os alcança. Quem conversa
com eles é o agente em `agente-acesso/`, que roda num mini-PC na quadra e busca o
estado desejado no servidor. Nunca escreva código no backend que fale direto com
um leitor — não há rota. Detalhes na seção 19 de `docs/SISTEMA.md`.

Os endpoints CGI estão conferidos contra a coleção Postman oficial da Intelbras
e o Portal de Integração, e ficam todos em `agente-acesso/driver.py`. A janela do
jogo é a **validade do usuário** no leitor (`ValidFrom`/`ValidTo`): quem impõe o
horário é o equipamento, não o agente. `python agente-acesso/teste_agente.py`
valida tudo contra leitores simulados, sem hardware.

## Convenções

- **Português** em código, comentários, commits e UI
- Fuso `America/Sao_Paulo`; banco em UTC, conversão na borda
- Migrations manuais e sequenciais (`alembic/versions/00NN_descricao.py`)
- `selectinload` para relações — lazy load quebra em async
- Dados do usuário passam por `esc()` / `escHtml()` antes de ir para `innerHTML`
- Enums do Postgres guardam o *value*; novo valor exige `ALTER TYPE ... ADD VALUE`
  (cada migration roda na própria transação, `alembic/env.py`)
- `admin.js` não usa `;`: linha que começa com `[` ou `(` gruda na de cima.
  Guarde o array numa constante antes de iterar

## Segurança

Credenciais (Asaas, Autentique, SMTP, senha do admin) ficam **apenas** no `.env`
do servidor. Nunca exibir, copiar ou registrar esses valores — nem em commits,
nem em documentação, nem na conversa.

## Ao concluir uma mudança

1. Atualize a seção correspondente em `docs/SISTEMA.md` (regra nova, modelo novo,
   migration, pendência resolvida)
2. Suba o `CACHE_NAME` se mexeu no frontend
3. Informe o comando de deploy correto para o caso (com ou sem migration)
