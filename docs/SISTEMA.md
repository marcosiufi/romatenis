# Sistema Roma Tênis — Referência Técnica

> Documento de referência do sistema. Mantido manualmente — ao mudar regra de
> negócio, modelo ou fluxo, **atualize a seção correspondente aqui**.
>
> Última atualização: migration `0030`, service worker `v59`.

---

## 1. Visão geral

PWA de gestão de um clube de tênis com quadra única, em Ribeirão Preto/SP.
Três produtos pagos convivem no mesmo calendário:

| Produto | Quem usa | Cobrança |
|---|---|---|
| **Ranking** | Membros com assinatura ativa | Plano mensal/trimestral/semestral/anual |
| **Locação avulsa** | Qualquer pessoa cadastrada | Por hora |
| **Jogo avulso** | Membro + convidado de fora | Por convidado |

Três interfaces, todas servidas pelo mesmo backend:

| Interface | Caminho | Público |
|---|---|---|
| Site institucional | `/` | Visitantes, contratação de plano, locação |
| App (PWA) | `/app/` | Membros do ranking |
| Painel administrativo | `/admin/` | Administradores |

---

## 2. Stack e infraestrutura

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic
- **Banco:** PostgreSQL 16
- **Frontend:** HTML/CSS/JS puro (sem framework, sem build step)
- **Proxy/TLS:** Caddy 2 (Let's Encrypt automático)
- **Deploy:** Docker Compose em VPS

### Serviços (`docker-compose.yml`)

| Serviço | Imagem | Observação |
|---|---|---|
| `db` | postgres:16-alpine | volume `pg_data` |
| `api` | build local | FastAPI + frontend estático, 2 workers uvicorn |
| `caddy` | caddy:2-alpine | portas 80/443, TLS automático |

**Só `./uploads` é montado como volume.** O `frontend/` é copiado para dentro
da imagem pelo `COPY . .` do Dockerfile — ver seção 11 (Deploy), é a causa da
armadilha mais importante do projeto.

### Servidor

- Host: `root@romatenis.com.br` (SSH com senha interativa)
- Caminho do projeto: `/opt/romatenis`
- Domínio: `romatenis.com.br` (DNS no Registro.br)

---

## 3. Estrutura de diretórios

```
app/
  main.py                 FastAPI + 2 loops de background (scheduler)
  core/
    auth.py               JWT, hash de senha, dependências de autenticação
    config.py             Settings (lê .env)
    database.py           engine async, Base, pg_enum
    validators.py         validação de CPF (dígitos verificadores)
  models/                 17 modelos SQLAlchemy
  schemas/                Pydantic (booking, cupom, match, player, season, subscription)
  services/               regra de negócio
  api/v1/                 rotas
alembic/versions/         30 migrations (0001 … 0030)
frontend/
  index.html              site institucional (JS inline)
  app/index.html          PWA do membro
  admin/index.html        painel administrativo (CSS inline)
  js/app.js               JS do app
  admin/js/admin.js       JS do admin
  css/style.css           app
  css/landing.css         site
  img/                    logos em PNG (usadas externamente)
  service-worker.js       cache do PWA — CACHE_NAME precisa subir a cada deploy
docs/SISTEMA.md           este documento
```

---

## 4. Modelos de dados

### Player
Jogador (membro ou apenas cadastrado). Campos principais:

- Identidade: `nome`, `apelido`, `email` (único), `telefone` (único), `cpf` (único), `data_nascimento`
- Endereço: `rua`, `numero`, `complemento`, `bairro`, `cidade`, `estado`, `pais`, `cep`
- Ranking: `rating_atual` (Elo, default 1000), `nivel` (A/B/C/D/nao_classificado),
  `pontos_ranking_temporada_atual`, `partidas_computadas_rating`
- Contrato: `contrato_autentique_id`, `contrato_link_assinatura`, `contrato_assinado`,
  `contrato_enviado_em`, `contrato_assinado_em`, `contrato_lembretes_enviados`,
  `contrato_ultimo_lembrete_em`
- Outros: `is_admin`, `status`, `foto_url`, `asaas_customer_id`, `reset_token`

**StatusJogador:** `ativo` · `assinatura` (aguardando assinar contrato) ·
`pagamento` (aguardando confirmação) · `renovacao` (expirado, 7 dias p/ renovar) · `inativo`

### Match / MatchParticipant
Partida e seus participantes.

- `tipo`: `simples` | `duplas`
- `status`: `agendado` | `realizado` | `cancelado_sem_placar` | `wo`
- `avulso` (bool): jogo avulso — não pontua, não aceita placar nem W.O.
- `lembrete_enviado` (bool): evita reenvio do lembrete pelo scheduler
- `cancelado_por_id` (FK player): **cancelamento tardio** — ver seção 5.4
- `placar` (JSON), `lado_vencedor` ("A"/"B"), `season_id`

`MatchParticipant` tem `player_id` **ou** `convidado_id` (exclusivos) + `lado` (A/B),
mais snapshot de `rating_antes`/`rating_depois`/`pontos_atribuidos`.

### Booking
Reserva de horário. `tipo`: `ranking` | `locacao_avulsa` | `jogo_avulso` | `aula`.
`status`: `aguardando_pagamento` | `confirmada` | `cancelada`.
Liga-se opcionalmente a `match_id` (1:1).

### Subscription
Assinatura do plano. `plano` (mensal/trimestral/semestral/anual),
`forma_pagamento` (pix_avista/boleto_avista/cartao_parcelado),
`status` (pendente/ativa/pausada/expirada/inadimplente/cancelada),
`data_inicio_ciclo`, `data_expiracao`, campos de pausa, flags `aviso_7d_enviado`/`aviso_1d_enviado`.

> **Boleto está desabilitado** no código (erro explícito em `criar_assinatura`).

### Payment
Cobrança. Pertence a `booking_id` **ou** `subscription_id`.
`metodo` (pix/cartao/boleto), `status` (pendente/pago/falhou/estornado),
`gateway_id` (id no Asaas), `cupom_codigo` + `valor_desconto` (snapshot, sem FK).

### Cupom
`codigo` (único, maiúsculo), `percentual` (1–100), `descricao`,
`validade_inicio`/`validade_fim` (opcionais), `max_usos` (opcional), `usos`, `ativo`.

### Convidado
Jogador de fora do ranking, em jogo avulso: `nome`, `cpf`, `whatsapp`,
`data_nascimento`, `apelido`. Propriedade `nome_exibicao` (apelido, ou primeiro+último nome).

### Configuracao
**Linha única (id=1)**, acessada por `Configuracao.get(db)`. Ver seção 6.

### Demais
`Season` (temporada + `ranking_final` em JSON), `ListaEspera`, `SlotRanking`
(janelas de ranking por dia da semana), `HorarioDiaSemana`, `HorarioEspecial`
(override por data), `Feriado`, `ContratoClausula`, `MatchInvitation` (matchmaking),
`WhatsAppMessageLog`.

---

## 5. Regras de negócio

### 5.1 Pontuação e classificação

```
Simples      → vencedor +100, perdedor +30
Simples W.O. → vencedor +100, perdedor −100
Duplas       → vencedor  +50, perdedor +15
Duplas W.O.  → vencedor  +50, perdedor  −50

Elo: K = 32 (< 20 partidas), K = 16 (≥ 20)
     Duplas: K/2, rating médio por lado
     W.O. NÃO afeta rating

Níveis (percentil): A = top 25% · B = 25–50% · C = 50–75% · D = 75–100%
                    Só para quem tem ≥ 5 partidas computadas
```

### 5.2 Limites de agendamento (ranking)

| Regra | Valor | Onde |
|---|---|---|
| Limite semanal simples | 3 jogos | `LIMITE_SEMANAL`, `booking_service.py` |
| Limite semanal duplas | 2 jogos | idem |
| Jogos ativos simultâneos | 1 por tipo | `_verificar_limite_ativo` |

- A semana é **segunda a domingo**, no fuso de Brasília.
- Jogo avulso **consome a mesma cota** do tipo correspondente.
- "1 ativo por tipo": não dá para marcar outro simples enquanto houver um simples
  agendado e não encerrado.

### 5.3 Janelas de horário e antecedência

Hierarquia de horário de funcionamento (mais específico vence):

```
HorarioEspecial (data)  >  HorarioDiaSemana (dia da semana)  >  fallback
```

`SlotRanking` define quais horas do dia são do ranking. Fora delas, o horário é
"comercial" — disponível para o membro só na janela de última hora.

Antecedências (todas configuráveis no admin — seção 6):

| Regra | Padrão |
|---|---|
| Ranking — antecedência mínima | 6h |
| Ranking — janela de última hora | 1h |
| Jogo avulso — janela de última hora | 1h |
| Locação — libera slot do ranking | 6h |
| Cancelamento sem penalidade | 3h |

**Ranking:** reserva normal com ≥ 6h; abaixo de 1h libera qualquer slot livre;
**entre 1h e 6h fica bloqueado** (janela morta). Validação garante
`última_hora < mínima` — igualá-las anularia a reserva antecipada.

**Jogo avulso:** só pode ser reservado dentro da janela de última hora.

### 5.4 Política de cancelamento

Vale para ranking e jogo avulso, prazo configurável (padrão 3h):

| Situação | Saldo semanal | Horário | Pontuação |
|---|---|---|---|
| Cancelou **≥ prazo** antes | não afeta | liberado | — |
| Cancelou **< prazo** antes | **abate de quem cancelou** | liberado | ninguém pontua |
| Admin cancela | não afeta | liberado | — |

No cancelamento tardio o match vira `wo` e `cancelado_por_id` recebe o id de quem
cancelou. Os **demais participantes recuperam a vaga** — só o autor perde.

A contagem semanal (`_contar_jogos_semana`) soma:
- partidas com reserva confirmada e `cancelado_por_id IS NULL`, com status ≠ cancelado; **mais**
- partidas onde `cancelado_por_id = <este jogador>`.

### 5.5 Jogo avulso

Membro joga com convidado(s) de fora. Regras:

- Só na janela de última hora, em qualquer slot livre
- Simples ou duplas; pode misturar membros e convidados nos dois lados
- **Não pontua para ninguém** (não aceita placar nem W.O.); `season_id = None`
- **Consome a cota semanal** do tipo, de cada membro envolvido
- Cobrança **por convidado**; o slot fica `aguardando_pagamento` e só é confirmado
  pelo webhook do Asaas
- Se a cobrança falhar, a reserva inteira é desfeita (rollback)
- Dados do convidado exigidos: nome completo, CPF (validado), WhatsApp, nascimento; apelido opcional

### 5.6 Cupons de desconto

- Percentual, com prazo e limite de usos opcionais
- Valem nos **três** fluxos pagos: planos, locação e jogo avulso
- **O cupom substitui o desconto de 5% do PIX** (não acumulam)
- `usos` é incrementado na criação da cobrança; **devolvido** se a pré-reserva
  expira sem pagamento (loop de 10 min)
- O backend revalida e recalcula no momento da cobrança — o valor nunca vem do cliente

### 5.7 Pré-reserva não paga

Locação avulsa e jogo avulso geram cobrança antes de confirmar. Enquanto
`aguardando_pagamento`, o slot fica **segurado por 10 minutos** (`JANELA_PRE_RESERVA`).
Passado esse prazo, um loop cancela a reserva, cancela a partida associada (se
houver) e cancela a cobrança no Asaas.

### 5.8 Lista de espera

Quando o ranking atinge `limite_ranking` (padrão 30), novas contratações são
bloqueadas e o interessado entra na fila. Ao abrir vaga, o primeiro da fila é
convocado por e-mail e tem **48h** para contratar. Convocação expirada libera a
vaga para o próximo (verificado de hora em hora pelo scheduler).

---

## 6. Configurações do admin (`Configuracao`, linha única)

| Grupo | Campos |
|---|---|
| Preços | `preco_mensal`, `preco_trimestral`, `preco_semestral`, `preco_anual`, `preco_locacao_hora`, `preco_jogo_avulso` |
| Disponibilidade | `contratacao_planos_ativa`, `reservas_ativas`, `msg_planos_desabilitado`, `msg_reservas_desabilitado` |
| Antecedências | `ranking_antecedencia_minima_horas`, `ranking_ultima_hora_horas`, `jogo_avulso_ultima_hora_horas`, `locacao_libera_slot_ranking_horas`, `cancelamento_antecedencia_horas` |
| Ranking | `limite_ranking` |
| Empresa | `razao_social`, `nome_fantasia`, `cnpj`, `cpf_responsavel`, endereço (8 campos), `whatsapp`, `instagram`, `email_contato` |
| Legado | `hora_abertura`, `hora_fechamento` — **não editáveis**, substituídos por `HorarioDiaSemana` |

### Toggles de pré-lançamento

Com `contratacao_planos_ativa` ou `reservas_ativas` **desligados**, o backend
responde **403** com a mensagem configurada. **Cadastro e lista de espera
continuam funcionando** — é o que permite divulgar antes de abrir.

No site, com planos desligados, os botões viram "Entrar na lista de espera" e o
403 leva ao passo de fila. Ligar o toggle de planos dispara e-mail para toda a
lista de espera (só na transição desligado → ligado).

---

## 7. Automações de e-mail

Todas em `app/services/email_service.py`. Estrutura MIME: **sempre `text/plain` +
`text/html`** — um `multipart/alternative` só com HTML é sinal de spam.

| E-mail | Gatilho |
|---|---|
| Boas-vindas | Cadastro público |
| Confirmação de pagamento | Webhook Asaas |
| Aviso de vencimento | Scheduler: 7 e 1 dia antes |
| Contrato pendente | Scheduler: 1 dia depois, a cada 3 dias, máx. 3 |
| Contrato assinado | Webhook Autentique |
| Convocação da lista de espera | Vaga aberta no ranking |
| Confirmação de entrada na fila | Entrou na lista de espera |
| Abertura de inscrições | Admin liga o toggle de planos |
| Lembrete de partida | Scheduler: até 3h antes do jogo |
| Aviso de pausa aprovada | Admin aprova pausa |
| Redefinição de senha | "Esqueci minha senha" |
| **Alerta ao admin** | Autentique falha ao enviar contrato |

`send_email` engole falhas (uso automático); `send_email_estrito` propaga
(usado pelo teste do painel).

### Configuração SMTP

Google Workspace com `contato@romatenis.com.br`, autenticando com **Senha de App**
(16 caracteres). Variáveis: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
`SMTP_FROM` (vazio = usa o SMTP_USER), `SMTP_FROM_NAME`.

**Diagnóstico:** Admin → Configurações → Envio de E-mails mostra o estado e envia
teste, com erros do SMTP traduzidos em instruções.

### DNS (todos configurados e validados)

| Registro | Valor |
|---|---|
| MX | 5 registros do Google (`aspmx.l.google.com` etc.) |
| SPF | `v=spf1 include:_spf.google.com ~all` |
| DKIM | `google._domainkey` (gerado no Admin Console) |
| DMARC | `v=DMARC1; p=none; rua=mailto:contato@romatenis.com.br` |

---

## 8. Jobs em background (`app/main.py`)

### `_scheduler_loop` — a cada 1 hora
1. `verificar_expiracoes` — assinaturas vencidas → EXPIRADA + jogador em RENOVACAO
2. `enviar_avisos_vencimento` — 7 e 1 dia antes
3. `resetar_nivel_inativos` — zera nível de quem tem < 5 partidas
4. `verificar_convocacoes_expiradas` — destrava a fila de espera
5. `enviar_lembretes_partida` — até 3h antes do jogo

### `_expirar_reservas_loop` — a cada 2 minutos
Cancela pré-reservas de **locação avulsa e jogo avulso** não pagas há mais de
10 min: cancela reserva, cancela partida associada, cancela cobrança no Asaas e
**devolve o uso do cupom**.

---

## 9. Integrações externas

| Serviço | Uso | Credencial |
|---|---|---|
| **Asaas** | Cobranças (PIX, cartão) | `ASAAS_API_KEY` (base64 no .env), `ASAAS_WEBHOOK_TOKEN` |
| **Autentique** | Contrato digital, enviado por WhatsApp | `AUTENTIQUE_API_KEY`, `AUTENTIQUE_WEBHOOK_SECRET` |
| **SMTP (Google)** | E-mails transacionais | `SMTP_*` |
| **WhatsApp (Meta)** | 4 notificações prontas — **credenciais vazias, inativo** | `WHATSAPP_*` |
| **N8N** | Matchmaking (webhooks) | `N8N_SECRET` |

> A chave do Asaas é guardada em **base64** no `.env` porque contém `$`, que o
> Docker Compose interpolaria. Decodificada em `settings.asaas_api_key`.

**Nenhuma credencial deve ser exibida ou copiada para fora do `.env` do servidor.**

---

## 10. API — mapa de rotas

Prefixo geral: `/api/v1`

| Router | Rotas |
|---|---|
| `auth` | `/login` `/refresh` `/me` `/esqueci-senha` `/validar-reset` `/redefinir-senha` `/alterar-senha` |
| `public` | `/disponibilidade` `/cadastro` `/reserva` `/empresa` `/temporadas` `/horarios-semana` |
| `players` | listar/criar · `/me` · `/me/foto` · `PATCH /me` · `/{id}` |
| `bookings` | `/slots` `/ranking` `/jogo-avulso` `/locacao` `/uso-semanal` `DELETE /{id}` `/feriados` |
| `matches` | listar · `/{id}/placar` `/{id}/wo` `/{id}/cancelar` (admin) `/{id}/cancelar-jogador` `/recalcular-classificacao` |
| `subscriptions` | `/contratar` `/renovar` `/precos` `/minhas` `/minha-ativa` `/pix-pendente` `/solicitar-pausa` `/lista-espera*` `/vagas-ranking` `/webhook` |
| `seasons` | listar · `/ativa` · criar · `/{id}/encerrar` |
| `cupons` | `POST /validar` (autenticado — preview do desconto) |
| `admin` | `/dashboard` `/players` `/configuracoes` `/cupons*` `/email/status` `/email/testar` `/slots-ranking*` `/horarios-especiais*` `/horarios-semana` `/lista-espera*` `/contrato/clausulas` `/empresa` |
| `webhooks` | `/webhooks/n8n/*` `/matchmaking/*` |

`GET /public/empresa` é o endpoint que o front usa para saber preços, estado
comercial (toggles + mensagens) e prazo de cancelamento.

---

## 11. Deploy — LEIA ANTES DE PUBLICAR

O `Dockerfile` faz `COPY . .`, então **o frontend é embutido na imagem**. O
Docker reaproveita a camada em cache e um `docker compose build` comum **não
recopia arquivos alterados** — o container continua servindo a versão antiga.

### Comando padrão (frontend, backend, ou ambos)

```bash
cd /opt/romatenis && git pull && docker compose build --no-cache api && docker compose up -d --force-recreate api
```

### Se o commit tiver migration

```bash
cd /opt/romatenis && git pull && docker compose build --no-cache api && docker compose up -d --force-recreate api && docker compose exec -T api alembic upgrade head
```

### Checklist ao mexer no frontend

1. Subir `CACHE_NAME` em `frontend/service-worker.js` (senão o PWA serve cache velho)
2. Deploy com `--no-cache`
3. **Ctrl+Shift+R** no navegador

### Diagnóstico quando "não aplicou"

```bash
cd /opt/romatenis && git rev-parse --short HEAD && sha256sum frontend/<arquivo> && docker compose exec -T api sha256sum /app/frontend/<arquivo>
```

Compare os três: commit certo, disco certo, **container diferente** = cache do
build. Resolva com `--no-cache`.

### Comandos úteis no servidor

```bash
docker compose logs --tail=80 api          # logs da API
docker compose exec api alembic current    # migration aplicada
docker compose exec api python scripts/seed_admin.py   # cria o primeiro admin
```

---

## 12. Convenções do projeto

- **Idioma:** código, comentários, commits e UI em **português**
- **Fuso:** `America/Sao_Paulo` (`FUSO_BR`); banco em UTC, conversão na borda
- **Migrations:** manuais, numeradas sequencialmente (`00NN_descricao.py`)
- **Enums no Postgres:** `pg_enum` grava o *value*, não o *name*.
  Adicionar valor exige `ALTER TYPE ... ADD VALUE IF NOT EXISTS` (ver `0016`, `0024`)
- **Eager loading:** `selectinload` — lazy load quebra em async
- **XSS:** dados do usuário passam por `esc()` (app) / `escHtml()` (admin) antes de `innerHTML`
- **CPF:** validado por dígitos verificadores no backend (`app/core/validators.py`) e no frontend
- **Commits:** mensagem em português, corpo explicando o *porquê*, com
  `Co-Authored-By` do modelo

### Paleta e tipografia

```
App / Admin (escala de superfícies, do fundo ao elevado)
  fundo       #0f1f15 (app) · #0c1a11 (admin)
  superfície  #1b3324 (app) · #162c1d (admin)
  elevado     #23422e (app) · #1d3826 (admin)

Marca        terracota #c0622a  ·  hover #d97742
Texto        #f0ebe4  ·  suave #a9c0b0  ·  fraco #7d9686
Semânticas   sucesso #5cc182 · aviso #e3ab4d · perigo #e8785f

Título: Cinzel 700 (serif romana)   Corpo: Inter 400/500/600/700
```

O tom secundário é **verde-acinzentado**, não o azulado `#9ab` anterior nem
branco transparente: harmoniza com o fundo em vez de brigar com ele. O site
(`landing.css`) mantém a própria paleta, mais escura, já alinhada à marca.

---

## 13. Pendências e limitações conhecidas

| Item | Situação |
|---|---|
| **WhatsApp** | 4 notificações implementadas, credenciais Meta vazias — nada é enviado |
| **Matchmaking** | Serviço existe, disparo manual pelo admin, depende de N8N |
| **`booking_service` ignora `HorarioDiaSemana`** | Usa 6–22 fixo como fallback, enquanto `public.py` respeita a config. Divergência entre app e site |
| **`hora_abertura`/`hora_fechamento`** | Vestigiais em `Configuracao`, mantidos só como fallback |
| **E-mail de abertura em lote** | Envio sequencial dentro da request; lista grande pode travar a tela e esbarrar no limite do Gmail |
| **Escape XSS** | Varredura completa feita na auditoria — sem pendências (seção 15) |
| **CSP** | Não há `Content-Security-Policy`; exigiria remover `onclick` inline |
| **Reputação de e-mail** | Domínio novo — mensagens podem cair em spam até criar histórico |

---

## 14. Histórico de migrations

| # | Conteúdo |
|---|---|
| 0001–0008 | Base: players, matches, bookings, subscriptions, feriados, matchmaking, foto, dados cadastrais |
| 0009–0015 | Configurações, contrato, slots de ranking, horário de funcionamento, horários especiais |
| 0016–0020 | Status `aguardando_pagamento`, `criado_em`, `pendente`, lista de espera, cláusulas |
| 0021–0023 | Horário por dia da semana, dados da empresa, endereço separado em 8 campos |
| 0024 | **Jogo avulso**: convidados, `Match.avulso`, participante convidado, preço |
| 0025 | **Toggles** de contratação/reservas + antecedências configuráveis |
| 0026 | Controle de lembretes de contrato |
| 0027 | `Match.lembrete_enviado` |
| 0028 | **Cupons** + snapshot no Payment |
| 0029 | **Política de cancelamento**: prazo configurável + `cancelado_por_id` |
| 0030 | **Constraint EXCLUDE** em bookings: impede reserva dupla no banco |

---

## 15. Auditoria de 30/08/2026 — falhas encontradas e corrigidas

Revisão sistemática do sistema por categoria (autorização, corrida, integridade
de dados, idempotência, XSS). Registro do que foi encontrado e como foi tratado.

### 15.1 Vazamento de dados pessoais (crítico)

`GET /api/v1/players` **não exigia autenticação** e devolvia `PlayerOut`, que
inclui `cpf`, `telefone`, `email`, `data_nascimento` e o endereço completo de
todos os membros. Qualquer pessoa na internet podia coletar esses dados com uma
requisição. Havia ainda uma exposição secundária: `GET /players/{id}` exigia
login, mas qualquer membro podia ler o cadastro completo de qualquer outro.

**Correção:** criado `PlayerRankingOut`, uma visão sem dados pessoais (id, nome,
apelido, foto, nível, rating, pontos, status). A listagem passou a exigir
autenticação e a usar essa visão; o endpoint individual só devolve `PlayerOut`
para o próprio jogador ou para admin.

> **Regra a manter:** `PlayerOut` é a visão privada. Nunca use em endpoint que
> outros jogadores possam ler.

### 15.2 Reserva dupla por condição de corrida (alto)

A checagem de sobreposição existia só na aplicação: `SELECT` para ver se o slot
está livre, depois `INSERT`. Duas requisições simultâneas passavam as duas —
alcançável com 2 workers uvicorn, sobretudo na disputa por um horário liberado
na janela de última hora.

**Correção:** constraint `EXCLUDE USING gist` sobre `tstzrange(inicio, fim)` para
reservas em `confirmada` ou `aguardando_pagamento` (migration 0030). A garantia
passa a ser do banco, então nenhuma corrida escapa. Usa intervalo, não hora de
início, para cobrir locações de 2–4 h. A violação é traduzida em mensagem de
negócio ("Este horário acabou de ser reservado por outra pessoa").

Nota: reservas que apenas encostam (14–15 h e 15–16 h) **não** conflitam —
`tstzrange` usa limites `[início, fim)`.

### 15.3 Webhook de pagamento não idempotente (alto)

O Asaas reenvia eventos e manda `PAYMENT_RECEIVED` e `PAYMENT_CONFIRMED` para a
mesma cobrança. O código reprocessava: e-mail de confirmação duplicado e, pior,
um retry tardio após estorno **reativaria** a assinatura cancelada.

**Correção:** guarda de idempotência — se o pagamento já está `PAGO`, o evento
de pagamento é ignorado.

### 15.4 Contador de cupom com read-modify-write (médio)

`registrar_uso` fazia `cupom.usos = cupom.usos + 1` em Python. Dois pedidos
simultâneos liam o mesmo valor e gravavam o mesmo número, permitindo estourar o
`max_usos`.

**Correção:** incremento atômico em SQL (`usos = usos + 1`) com o limite na
cláusula `WHERE`; `rowcount == 0` significa que a última vaga acabou de ser
consumida e vira `CupomError`. Criado `devolver_uso` com a mesma abordagem, usado
pelo loop de expiração.

### 15.5 Cobrança órfã ao esgotar cupom (médio — introduzido por 15.4)

Como `registrar_uso` passou a poder falhar, e era chamado **depois** de criar a
cobrança no Asaas, uma corrida pela última vaga deixaria uma cobrança sem reserva
— o cliente poderia pagar por algo que não existe.

**Correção:** o consumo da vaga foi movido para **antes** da criação da cobrança
nos três fluxos (assinatura, locação, jogo avulso). Como é um `UPDATE` na mesma
transação ainda não commitada, qualquer falha posterior desfaz o incremento pelo
rollback.

> **Regra a manter:** nada que possa falhar deve ficar entre a criação da
> cobrança e o commit.

### 15.6 Ajustes menores

- `GET /bookings/feriados` estava marcado como `tags=["admin"]` mas não exigia
  autenticação, ao contrário do `POST` e do `DELETE` irmãos — corrigido.
- Código de cupom passou a ser escapado no site. Não era explorável (o backend
  restringe a alfanumérico, hífen e underline), mas o render deixa de depender
  desse invariante distante.

### 15.7 Crash latente com convidado no processamento de resultado (baixo)

`_processar_resultado` faz `by_id[part.player_id]`, e convidado tem
`player_id = None` — o que daria `KeyError: None` **no meio das mutações**,
deixando pontos e rating pela metade. Hoje não acontece, porque placar e W.O.
rejeitam partida avulsa e convidados só existem em partida avulsa. Mas o
invariante mora longe de quem depende dele.

**Correção:** guarda no início de `_processar_resultado` que falha cedo com
`MatchError` claro se algum participante não tiver `player_id`.

### 15.8 Verificado e correto (sem alteração)

- **Autenticação:** os únicos endpoints públicos restantes são intencionais —
  `precos` e `vagas-ranking` (informação pública) e `webhook` (validado por token
  no header).
- **XSS:** varredura completa em `app.js`, `admin.js` e `index.html` — sem
  pendências. O `instagram` no site vai para `href` com prefixo `https://` fixo
  e para `textContent`, ambos seguros por construção.
- **Cadeia de migrations:** 30 migrations, linear de 0001 a 0030, sem
  ramificação nem órfãs.
- **Sobreposição na aplicação:** a lógica de `_slot_ocupado` e a do `public.py`
  já cobriam corretamente reservas multi-hora; a falha era só a janela de corrida.
- **`expire_on_commit=False`** no sessionmaker: objetos não expiram após commit
  (uma anotação antiga afirmava o contrário e estava errada).
- **Matemática do ranking:** 30 casos testados nas funções puras — validação
  Set Pro (8-6, 9-7, 8-8 com tiebreak, e as rejeições: 8-7, 9-8, 10-8, tiebreak
  fora do 8-8, tiebreak empatado), expectativa de Elo (simetria e soma 1),
  fator K (32 abaixo de 20 partidas, 16 a partir de 20, metade em duplas) e as
  quatro tabelas de pontos. Todos corretos.
- **`recalcular_classificacao`:** sem divisão por zero com lista vazia; os
  percentis distribuem corretamente. Note que a reclassificação **não** é
  automática após cada partida — depende do botão no painel.
- **`_notificar_resultado`:** já ignora convidados com segurança
  (`by_id.get(...)` seguido de `continue`).

### 15.9 Atenção no deploy da migration 0030

**Predicado sem cast.** O PostgreSQL exige funções `IMMUTABLE` em predicado de
índice, e `status::text` é apenas `STABLE` (rótulos de enum podem ser
renomeados). A comparação é feita direto com os literais do enum
(`status IN ('confirmada', 'aguardando_pagamento')`), cuja igualdade é
imutável. A primeira tentativa usava o cast e falhou com
`functions in index predicate must be marked IMMUTABLE`.

A constraint só pode ser criada se **não houver sobreposição pré-existente**
entre reservas ativas. A migration verifica isso antes e falha com uma mensagem
dizendo quantos pares estão em conflito, em vez de criar a constraint pela
metade. Se isso acontecer, cancele as reservas duplicadas no painel e rode o
`alembic upgrade head` de novo.

---

## 16. Redesign de interface — 30/08/2026

Modernização do app do associado (web e mobile) e do painel admin, respeitando
a identidade visual. Ponto de retorno: tag `pre-redesign-2026-08-30` e cópia do
frontend em `Desenvolvimento/Backups/frontend-pre-redesign-2026-08-30/`.

### 16.1 Sistema de design

`frontend/css/style.css` foi reescrito em torno de tokens; o `<style>` do admin
ganhou um bloco de refinamento sobre a base existente. Ambos passaram a ter:

- **Escala de superfícies** (fundo → superfície → elevado). O fundo ficou mais
  profundo para os cards ganharem separação real — antes card e fundo eram tons
  quase iguais e a hierarquia sumia.
- **Escala de espaçamento** de base 4px (`--e1` … `--e8`), no lugar de valores
  soltos.
- **Escala de raio e elevação** (`--r-sm/md/lg/full`, `--sombra-1/2`).
- **Tipografia da marca**: Cinzel nos títulos, Inter no corpo. As duas fontes já
  eram carregadas nos dois painéis, mas o CSS usava Segoe UI em tudo — a
  identidade estava paga e ociosa. Os pesos do Inter passaram de só 500 para
  400/500/600/700.

Os nomes de variáveis antigos (`--cor-terracota` etc.) viraram aliases dos novos,
para não quebrar os estilos inline espalhados pelo HTML e pelo JS.

### 16.2 Alinhamentos corrigidos

- **Badges dos horários**: cada rótulo tinha a largura do próprio texto e ficava
  encostado à direita, deixando a borda esquerda irregular. A coluna passou a ter
  largura fixa (7rem) com o rótulo ocupando 100% dela — os cinco badges agora têm
  borda esquerda, direita e largura idênticas (verificado: 214/326/112px).
- **Topo da sidebar do admin**: marca, usuário e botão de recolher empilhavam em
  coluna e o "Sair" flutuava solto enquanto o nome não carregava. Agora marca e
  botão de recolher dividem a primeira linha, e o usuário fica abaixo.
- **Linhas do perfil**: rótulo à esquerda, valor à direita com quebra controlada
  para endereços longos.
- **Nav e header no desktop**: a barra ocupava a largura toda enquanto o conteúdo
  tinha 640px, deixando os itens espalhados e desconectados. O fundo continua
  cheio, mas os itens passaram a seguir a coluna do conteúdo.

### 16.3 Mobile

- Alvos de toque de no mínimo 44px em botões, campos e itens da navegação.
- Campo de formulário com altura mínima consistente.
- Item ativo da navegação com barra indicadora e cor de marca, além do ícone.
- `padding-bottom` do `main` calculado a partir da altura da barra + safe area,
  para o último item nunca ficar sob a navegação. A regra do desktop desfazia
  isso — ver 16.5.
- Modalidade (simples/duplas) virou chip selecionável, com área de toque maior e
  estado selecionado explícito, em vez de um radio pequeno.
- `env(safe-area-inset-*)` no header e na navegação, para aparelhos com notch.
- Animação de troca de tela respeitando `prefers-reduced-motion`.

### 16.4 Armadilhas encontradas na verificação

Duas classes de erro que só apareceram ao conferir contra a marcação real:

- **Regras mortas por seletor errado**: `.stat-card .num` (a classe real é
  `.valor`), `.busca-input` (os campos usam id) e `.modal-card` (a classe real é
  `.modal`). O CSS era válido e silencioso — parecia aplicado, mas não fazia nada.
  Corrigido conferindo cada seletor com `querySelectorAll` no DOM real.
- **Cache do service worker e do navegador** mascara mudanças de CSS: sem furar o
  cache, a verificação avalia a versão antiga e conclui que "nada mudou".

> **Ao mexer em CSS:** confira os seletores contra o DOM real antes de dar por
> pronto, e fure o cache ao verificar.

### 16.5 Espaçamento — correções de 30/08/2026 (pós-redesign)

Dois defeitos reportados no uso real, com a mesma consequência visual: caixas
encostadas e fim de página inalcançável.

**1. Fim do conteúdo escondido sob a barra de navegação (desktop)**

O `main` reservava a folga da barra fixa em `padding-bottom`, mas o bloco
`@media (min-width: 720px)` redeclarava a caixa toda com o **atalho**
`padding: var(--e6) var(--e6) var(--e8)`. O atalho reescreve os quatro lados: a
folga caía de 85px para 32px, contra uma barra de **61px**. Resultado: mesmo com
a rolagem no fim, 35px do último card ficavam sob a barra — o card parecia
cortado e "grudado" nela, e o conteúdo era inalcançável.

Corrigido com um token dedicado, usado nos dois lugares:

```css
--folga-nav: calc(var(--nav-h) + 1px + env(safe-area-inset-bottom) + var(--e6));
```

O `+ 1px` é a borda superior da nav — `--nav-h` é o `min-height` do item, não a
altura da barra.

> **Regra:** o `padding-bottom` do `main` sempre sai de `--folga-nav`. Nunca
> redeclare o padding do `main` com o atalho `padding:` sem repetir o token.

**2. Cards colados por reset de `:last-child`**

`.card:last-child { margin-bottom: 0 }` e `.partida-card:last-child { … }`
existiam para evitar sobra no fim da página. Mas quase todo card do app vive
dentro de um wrapper de passo — `#slots-container`, `#form-reserva`,
`#form-placar`, `#loc-s2`, `#loc-s3`, `#loc-s4` — e é sempre `:last-child` **do
wrapper**. Quando dois wrappers aparecem juntos (horários + confirmação, lista de
partidas + placar), as bordas ficavam com **0px** entre elas.

Os dois resets foram removidos: todo card mantém a margem, e o `padding-bottom`
do `main` já absorve a sobra do último. `#form-placar` recebeu `margin-top` de
16px cheios porque a margem **colapsa** com a do último `.partida-card` — 8px lá
não somariam 16px, resolveriam em `max(8, 8)`.

Os resets de `:last-child` que sobraram (`.ranking-item`, `.perfil-linha`,
`.slot-item`, `.uso-linha`) atuam em linhas dentro de um mesmo card e estão
corretos.

**Verificação** (agendar, partidas e locação, com os passos visíveis
simultaneamente, em 375px e 900px): espaçamento uniforme de 16px entre blocos e
8px no ritmo da lista de partidas; folga de 34px entre o último card e a barra;
rolagem alcançando o fim; sem rolagem horizontal.

O admin não tem o mesmo problema: `#admin-app` é `position: fixed; inset: 0`,
`.admin-main` rola internamente e nada fixo cobre o rodapé.

## 17. Painel administrativo — redesign com temas, 05/09/2026

O `<style>` de `frontend/admin/index.html` estava em duas camadas empilhadas: a
base original e um bloco de refinamento acrescentado em 30/08. Regras
concorrentes, dois conjuntos de tokens e nenhum caminho para tema claro. O bloco
foi reescrito como um sistema único.

### 17.1 Tema claro e escuro

Três estados, guardados em `localStorage` sob a chave `tema`:

| valor | comportamento |
|---|---|
| `auto` (padrão) | segue a configuração do sistema operacional |
| `claro` | claro fixado pelo usuário |
| `escuro` | escuro fixado pelo usuário |

O CSS lê o atributo `data-tema` do `<html>`; no modo automático o atributo é
**removido**, e aí só `prefers-color-scheme` decide:

```css
:root { /* tokens claros */ }
@media (prefers-color-scheme: dark) {
  :root:not([data-tema="claro"]) { /* tokens escuros */ }
}
:root[data-tema="escuro"] { /* tokens escuros */ }
```

Os tokens escuros aparecem duas vezes de propósito. Sem o bloco do atributo,
fixar "claro" num sistema escuro não venceria a media query — e sem o `:not()`,
fixar "claro" seria ignorado. O trio de regras cobre as quatro combinações.

O módulo de tema é um `<script>` **inline no `<head>`**, não em `admin.js`:
`admin.js` carrega no fim do `<body>`, e aplicar o tema depois da primeira
pintura faz a página piscar no tema errado.

O botão fica no rodapé da barra lateral e cicla os três estados.

O fundo escuro subiu de `#0c1a11` para `#14241b` — o anterior era quase preto e
achatava a hierarquia entre fundo, card e superfície elevada.

### 17.2 Barra lateral

- Doze itens soltos viraram **cinco grupos** rotulados (Visão geral, Ranking,
  Financeiro, Operação, Ajustes).
- Cada item ganhou **ícone SVG** com `stroke="currentColor"`. Isso torna o modo
  recolhido utilizável de verdade: antes ele escondia o rótulo com
  `font-size: 0` e mostrava a primeira letra via `::first-letter`.
- Usuário, tema e "Sair" saíram do topo apertado para um **rodapé fixo**, com
  avatar de inicial. `admin.js` preenche `#admin-inicial` junto com `#admin-nome`.
- Recolhida: 62px, ícones centralizados, rótulos de grupo viram separadores.

### 17.3 Alinhamento dos campos

Medido no DOM real, antes da correção:

- `select` da barra de filtros: **30px**, ao lado de campos de **40px**. O bloco
  de refinamento de agosto listava `#busca-jogador` e `#filtro-sub-nome` por id,
  então só esses dois campos recebiam altura — os selects ficavam de fora.
- Botões: 33px na mesma linha de campos de 40px.
- `.form-grid-2` e `.form-grid-4`: `gap: 0 1rem`, ou seja **row-gap zero**; o
  espaço entre linhas vinha da margem do `.form-row`.

Agora existe um token único, `--h-controle: 40px`, aplicado a input, select,
textarea e aos controles das barras de filtro e de cabeçalho de seção; as grades
têm row-gap próprio e `align-items: start`. Verificado: todo controle em 40px e
desvio zero entre campos da mesma linha, nas três grades do painel.

### 17.4 Contraste

Conferido com cálculo WCAG contra o fundo real (inclusive o fundo tingido do item
ativo, que é translúcido sobre a superfície). Quatro ajustes foram necessários:

- `--texto-fraco` do tema claro: `#65806f` dava 4.06:1 no cabeçalho de tabela →
  `#5a7364` (4.86:1).
- `--texto-fraco` do tema escuro: `#8ba394` dava 4.02:1 → `#9db5a5` (5.10:1).
- O rótulo do item ativo usava a cor da marca sobre o próprio fundo tingido:
  3.6:1 no escuro. A marca ficou no **ícone e na barra lateral** — elementos
  gráficos, que pedem 3:1 — e o rótulo passou a usar tinta cheia (9.3:1 no
  escuro, 13.5:1 no claro).

Menor razão de texto hoje: 4.86:1.

### 17.5 Cores fixas no JavaScript

`admin.js` escrevia cores de status direto no `style` inline (`#4ab870`,
`#e0a040`, `#e06060`…), todas claras, pensadas só para fundo escuro — no tema
claro ficariam ilegíveis sobre o branco. As 25 ocorrências viraram
`var(--ok)`, `var(--aviso)` e `var(--perigo)`.

Os fundos sólidos de badge (`#2a6e3a`, `#1a3d6e`, `#7a3c00`…) continuam fixos:
são pílulas saturadas com texto branco, legíveis nos dois temas.

### 17.6 Regras mortas encontradas

Cinco classes geradas por `admin.js` não tinham regra nenhuma:
`.data-table`, `.contrato-clausula-card`, `.ct-titulo`, `.ct-texto`, `.ct-ativo`.
Todas receberam estilo.

> **Ao mexer no CSS do admin:** os nomes antigos (`--clr-bg`, `--clr-accent`…)
> sobrevivem como **aliases** dos tokens novos, porque o HTML e o `admin.js`
> têm estilos inline que ainda os usam. Não remova os aliases.

## 18. Temas no app do associado — 05/09/2026

O mesmo par de temas da seção 17, agora em `frontend/css/style.css` e
`frontend/app/index.html`. Mesma mecânica (`localStorage.tema` com
`auto` | `claro` | `escuro`, atributo `data-tema` no `<html>`, script inline no
`<head>`) e **a mesma paleta** — app e admin compartilham os valores.

### 18.1 Onde o usuário troca

Um cartão **Aparência** na tela de Perfil, com três opções em botões
segmentados. O admin usa um botão que cicla; aqui há espaço para mostrar as três
de uma vez, o que é mais claro no celular.

Extras que o app precisa e o admin não:

- **`<meta name="theme-color">`**: a barra de status do PWA acompanha
  `--superficie`. O script atualiza a meta a cada troca de tema.
- **`matchMedia('(prefers-color-scheme: dark)')`**: no modo automático o app
  reage se o sistema mudar de tema com o app aberto — em celular isso acontece
  sozinho no fim do dia.

### 18.2 Cores que só funcionavam no escuro

O CSS e o `app.js` tinham valores fixos pensados só para fundo escuro. Sobre
branco eles sumiriam ou ficariam ilegíveis. Todos viraram tokens:

| antes | agora |
|---|---|
| `rgba(255,255,255,.05 … .10)` (fundos de badge, trilhas, hover) | `--superficie-sutil`, `--realce`, `--pressionado` |
| `rgba(0,0,0,.28)` (caixa do código PIX) | `--fundo-codigo` |
| `rgba(255,255,255,.07)` (campo em foco) | `--campo-fundo-foco` |
| `#e8905a` (texto sobre tinta terracota) | `--terracota` |
| `rgba(227,171,77,.18)` etc. (tintas semânticas) | `color-mix(in srgb, var(--aviso) 12%, transparent)` |
| 8 cores fixas em `style` inline no `app.js` | `var(--aviso)`, `var(--terracota)`, `var(--sucesso)`… |

O `fill="#F0EBE4"` do "ROMA" no logo SVG (login e cadastro) virou
`fill="var(--texto)"` — em creme sobre fundo claro ele desaparecia.

### 18.3 Botão x tinta

`--terracota` era usada tanto como fundo de botão (com texto branco) quanto como
cor de texto. Não dá para servir aos dois no escuro: o tom que contrasta com a
superfície não contrasta com o branco por cima dele. Separado em
`--terracota` (tinta e elementos gráficos) e `--btn-fundo` / `--btn-fundo-hover`
/ `--btn-texto` (botão), como já era no admin.

### 18.4 Contraste

Medido com cálculo WCAG contra o fundo **achatado** — as tintas são
translúcidas, então comparar com a cor declarada dá um número otimista. Onze
componentes por tema. Seis reprovaram na primeira medição, todos por tinta
semântica sobre a própria tinta, que tem contraste limitado por construção.

Correções, aplicadas **também no admin** para as duas telas manterem a mesma
paleta:

| token | antes | depois |
|---|---|---|
| `--terracota` (claro) | `#a8511d` | `#94461a` |
| `--terracota` (escuro) | `#d2743a` | `#e79a63` |
| `--terracota-fraco` (escuro) | 16% | 12% |
| `--texto-fraco` (claro) | `#5a7364` | `#4f6659` |
| `--sucesso` / `--ok` (claro) | `#1f7a45` | `#166034` |
| `--aviso` (claro) | `#96631a` | `#734a0b` |
| `--perigo` (claro) | `#b3372a` | `#9c2b20` |
| tintas semânticas | 16% | 12% |

Menor razão de texto: **4.78:1** no app, **5.10:1** no admin.

> A landing (`frontend/css/landing.css`) **não** foi tocada: tem tokens próprios
> e segue só no escuro, que é a identidade do site.

