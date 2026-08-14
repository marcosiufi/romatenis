# Sistema Roma Tênis — Referência Técnica

> Documento de referência do sistema. Mantido manualmente — ao mudar regra de
> negócio, modelo ou fluxo, **atualize a seção correspondente aqui**.
>
> Última atualização: migration `0029`, service worker `v57`.

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
alembic/versions/         29 migrations (0001 … 0029)
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
Verde escuro  #1a3320    Verde profundo #07100a
Terracota     #C1502E    Claro          #F0EBE4
Título: Cinzel (serif romana)   Corpo: Inter / Segoe UI
```

---

## 13. Pendências e limitações conhecidas

| Item | Situação |
|---|---|
| **WhatsApp** | 4 notificações implementadas, credenciais Meta vazias — nada é enviado |
| **Matchmaking** | Serviço existe, disparo manual pelo admin, depende de N8N |
| **`booking_service` ignora `HorarioDiaSemana`** | Usa 6–22 fixo como fallback, enquanto `public.py` respeita a config. Divergência entre app e site |
| **`hora_abertura`/`hora_fechamento`** | Vestigiais em `Configuracao`, mantidos só como fallback |
| **E-mail de abertura em lote** | Envio sequencial dentro da request; lista grande pode travar a tela e esbarrar no limite do Gmail |
| **Escape XSS** | Aplicado nos pontos críticos; varredura completa do restante não foi feita |
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
