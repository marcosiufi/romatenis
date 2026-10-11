# Design do Roma Tênis — a gramática da Apple, na web

> Criado em 11/10/2026, no redesign pedido pelo Marco: "layout e design
> inspirados na Apple, mantendo o padrão de cores", como foi feito no SIUFI.
> O pedido veio com um prompt escrito para SwiftUI; este documento é a
> **tradução** para o que o Roma é: um PWA em HTML/CSS/JS sem build.
>
> Referência irmã, já aprovada: `docs/DESIGN.md` do SIUFI. O Roma segue a mesma
> gramática — com uma diferença que muda tudo: **o app do associado é usado no
> iPhone**, então ele fala a língua do iOS; o **painel admin é usado no
> Windows**, então ele fala a língua do macOS, como o SIUFI.
>
> Tela nova segue isto aqui. Na dúvida entre "fica bonito" e "segue a regra",
> segue a regra e discute a regra.

---

## 1. Os seis princípios, traduzidos

| Princípio da Apple | O que vira no Roma |
|---|---|
| **Integridade estética** | Clube de tênis: sóbrio, esportivo, sem enfeite. Cor só onde se toca ou onde algo está selecionado. Títulos em tinta neutra. A marca aparece inteira em um lugar por tela, no máximo (o cartão da assinatura, o login). |
| **Consistência** | Um componente para cada coisa. O mesmo controle segmentado onde se escolhe "um entre poucos" (Simples/Duplas, tema, período). A mesma linha de lista em ranking, partidas, perfil e transações. |
| **Manipulação direta** | O polegar do segmentado desliza; a linha da lista escurece no toque; a folha sobe do pé da tela no iPhone. |
| **Feedback** | Todo controle tem estado de toque, foco e desabilitado; carregamento com o indicador de oito raios; erro no contexto, em vermelho, com o que fazer. |
| **Metáforas** | Lista agrupada (os Ajustes do iPhone), cartão da carteira (a assinatura como um passe do Wallet), folha, interruptor, trilho e polegar. |
| **Controle do usuário** | Ação destrutiva é vermelha e pede confirmação num **alerta próprio** — nunca o `confirm()` do navegador, que aparece como "localhost diz…". Folha fecha no Esc, no toque fora e no "Cancelar". |

## 2. O que NÃO se traduz literalmente (e por quê)

- **SF Pro** tem licença só para as plataformas da Apple — mas a web pode
  **pedir a fonte do sistema** sem distribuí-la: `-apple-system` desenha em SF
  Pro no iPhone e no Mac, que é o próprio texto do aparelho. No Windows e no
  Android cai para **Inter** (desenho mais próximo do SF), servida pelo próprio
  sistema em `/fonts` — o Google Fonts levaria o IP de cada associado para um
  terceiro. Dinheiro usa `ui-rounded`: no aparelho Apple é o **SF Pro Rounded**
  dos saldos do Apple Card.
- **SF Symbols** não podem ser usados fora das plataformas Apple. Ícones são
  SVG em linha com o desenho do SF: traço de 1,75, pontas e junções
  arredondadas, sempre em `currentColor`.
- **Cinzel** é a marca, não a interface: fica só no logotipo ROMA. Título de
  tela é a fonte do sistema, como em qualquer app da Apple.
- **Dynamic Type** é real no iPhone: `font: -apple-system-body` no `<html>` faz
  o tamanho de texto escolhido nos Ajustes do aparelho escalar o app inteiro,
  porque toda medida de texto está em `rem`. Só no iOS — no Mac o "body" do
  sistema é 13 pt, pequeno demais para a web. Nos outros, o zoom do navegador
  faz o mesmo papel.
- **Haptics** não existem na web do iPhone. O feedback é visual: estado de
  toque imediato e movimento curto.
- **Materiais (vidro)** só nas barras fixas — barra de abas, barra de
  navegação, barra lateral. Desfoque em cartão custa bateria e não acrescenta.

## 3. Duas línguas: iOS no app, macOS no admin

| | App do associado (iOS) | Painel admin (macOS) |
|---|---|---|
| Texto padrão | 17 px (Body) | 13 px (o "regular" do macOS) |
| Alvo de toque | **44 px** mínimo | 32 px; pequeno 28, grande 40 |
| Navegação | barra de abas no pé + título grande | barra lateral + barra de ferramentas |
| Lista | agrupada com recuo (inset grouped) | tabela e lista de origem |
| Modal | folha que sobe do pé, com puxador | folha centralizada |
| Campo | 17 px — abaixo de 16 o Safari dá zoom ao focar | 13 px, 32 px de altura |

## 4. Tipografia

Estilos com nome de **papel**, os mesmos da Apple. Tamanhos em `rem` (relativos
ao Body), então o Dynamic Type do iPhone e o zoom do navegador escalam tudo.

### App (iOS) — `frontend/css/style.css`

| Token | iPhone (pt) | Uso |
|---|---|---|
| `--t-titulo-grande` | 34 / 41, bold | o título grande da tela |
| `--t-titulo-1` | 28 / 34, bold | número de destaque (saldo do jogo, valor) |
| `--t-titulo-2` | 22 / 28, bold | título de folha |
| `--t-titulo-3` | 20 / 25, semibold | título de seção grande |
| `--t-destaque` | 17 / 22, semibold | o "Headline": nome na linha, botão |
| `--t-corpo` | 17 / 22 | texto, campo, valor na linha |
| `--t-chamada` | 16 / 21 | texto de apoio maior |
| `--t-sub` | 15 / 20 | subtítulo de linha, rótulo de segmentado |
| `--t-nota` | 13 / 18 | rodapé de grupo, cabeçalho de seção |
| `--t-legenda` | 12 / 16 | meta, etiqueta |
| `--t-legenda-2` | 11 / 13 | rótulo da barra de abas — **mínimo absoluto** |

### Admin (macOS) — `<style>` de `frontend/admin/index.html`

A escala do SIUFI, para os dois sistemas terem a mesma régua: legenda 11 ·
nota 12 · **chamada 13 (o padrão)** · corpo 14 · título-3 15 · título-2 17 ·
título-1 22 · título-grande 28.

- Peso: 400 texto, 500 rótulo e botão, 600 título e número, 700 só no título
  grande. **Nada de caixa alta corrida** — cabeçalho de seção e de tabela é
  caixa de frase.
- Número que se compara em coluna leva `font-variant-numeric: tabular-nums`.
- Dinheiro: `ui-rounded`, tabular, peso 600.

## 5. Cor

Nomes de **papel**, com valor claro e escuro. A marca não muda; o que muda com
a aparência são os papéis.

| Papel | Claro | Escuro | O que é |
|---|---|---|---|
| `--plano` | `#F1F4F2` | `#0D1310` | o fundo (systemGroupedBackground) — cinza esverdeado, não creme |
| `--superficie` | `#FFFFFF` | `#18201C` | a célula, o grupo |
| `--elevado` | `#FFFFFF` | `#232C27` | folha, menu, alerta — no escuro, mais alto = mais claro |
| `--tinta` | `#111A15` | `#F2F5F3` | rótulo primário |
| `--tinta-2` | `#55625B` | `#A9B5AF` | secundário |
| `--tinta-3` | `#6B7770` | `#87948E` | terciário — **AA**, ao contrário da Apple |
| `--linha` | translúcida | translúcida | separador |
| `--preenche` 1·2·3 | translúcidos | translúcidos | os "fills": trilho, toque, botão cinza |
| `--tint` | saibro escuro | saibro claro | **o primário**: botão, link, seleção, foco, aba ativa |
| `--sobre-tint` | branco | marrom-escuro | texto sobre o tint cheio |
| `--marca-verde` | `#173A27` | igual | superfície de marca — não muda no escuro |
| `--marca-saibro` | `#C0622A` | igual | o saibro da marca |
| `--bom`, `--alerta`, `--critico` | | | estados |

O **saibro é o tint** — a cor da quadra de terra batida, que é o que o laranja
da marca é. O **verde é a superfície de marca**.

- **Cor só onde se toca.** Título não é colorido; seção não tem linha laranja.
- **Nenhum hexadecimal fora dos blocos de token.** Inclusive no JS — estilo
  inline com cor quebra um dos dois temas.
- Tinta sobre fundo tingido usa `color-mix()`, nunca `rgba` fixo.

## 6. O detalhe que é só do Roma

**As linhas da quadra.** Nas superfícies de marca (cartão da assinatura, login)
o verde leva o desenho fino de uma quadra de tênis vista de cima — linha de
fundo, linha de saque, marca central. É o único ornamento do sistema; fora
dessas superfícies, nada de textura, gradiente ou ilustração.

## 7. Estrutura das telas

### App

```
┌──────────────────────────────────┐  ← área segura do topo
│ ROMA                         (AP)│  barra de navegação: material translúcido
│                                  │  aparece quando o título grande sai da tela
│ Ranking                          │  ← título grande
│ Temporada de 22 ago a 21 nov     │
│ ╭──────────────────────────────╮ │
│ │ 1  (AP)  Aninha   Você   148 │ │  lista agrupada com recuo
│ │ 2  (BR)  Brunão          131 │ │  separador recuado até o texto
│ ╰──────────────────────────────╯ │
├──────────────────────────────────┤
│  Ranking Agendar Partidas Alugar │  barra de abas: material + área segura
└──────────────────────────────────┘
```

- O avatar no canto superior direito abre a conta (como na App Store). **Sair**
  fica no fim da conta, em vermelho — nunca na barra de cima.
- O título grande rola com a página; quando some, reaparece pequeno no centro
  da barra, que ganha o material e o separador.

### Admin

```
┌ barra lateral 240 ──────────┬────────────────────────────────────────────┐
│ ROMA TÊNIS             [⊟]  │ [barra presa: título pequeno ao rolar · ações] │
│ Visão geral                 │ Financeiro                                  │
│   ◫ Painel                  │ ‹ Outubro de 2026 ›     [Mês │ Ano]          │
│ Financeiro                  │ conteúdo                                    │
│   ◷ Resumo  ← selecionado:  │                                             │
│     preenchimento cinza     │                                             │
│ (M) Marco                   │                                             │
└─────────────────────────────┴────────────────────────────────────────────┘
```

- Ícones da barra lateral em tint; o item selecionado ganha **preenchimento
  cinza**, não cor (como o Finder).
- Uma barra de ferramentas por tela, logo abaixo do título.

## 8. Financeiro

O dinheiro do clube com a linguagem do Apple Card e do Wallet:

- **Valor recebido** em destaque, em `ui-rounded`, com o período ao lado.
- **Composição** numa barra só, dividida em planos, locações e jogos avulsos —
  como as categorias de gasto do Apple Card.
- **Atividade mensal** em barras; o mês escolhido no tint, os outros em
  preenchimento.
- **Transações** agrupadas por dia ("Hoje", "Ontem", "Sexta-feira, 9 de
  outubro"), com ícone em quadrado de cantos contínuos por categoria, valor à
  direita, e etiqueta só quando o pagamento não está em ordem.
- **Detalhe** de uma transação numa folha, como no Wallet.

No app, a assinatura é um **passe do Wallet**: o cartão verde com as linhas da
quadra, o plano, a validade e quanto falta; o histórico de pagamentos logo
abaixo, no mesmo desenho de transação.

## 9. Componentes

| Componente | Regra |
|---|---|
| Botão | `.btn-primario` (filled, tint), `.btn-secundario` (gray fill), `.btn-texto` (plain), `.btn-perigo`. App: 50 px de altura nos botões de largura total, 44 nos demais. Uma ação primária por região. |
| Lista | `.grupo` (inset grouped) com `.linha`; separador recuado até o texto; `.linha-nav` ganha o chevron. |
| Segmentado | escolha de UM entre 2–5. Trilho em preenchimento, polegar branco (no escuro, um degrau acima do trilho) que desliza com mola. |
| Interruptor | liga/desliga que vale **na hora**. Para escolha que só vale ao salvar, caixa de seleção. |
| Folha | iPhone: sobe do pé, cantos de 14 px, puxador; desktop: centralizada. Fecha no Esc e no toque fora. |
| Alerta | substitui `confirm()`. Título, mensagem, botões; o destrutivo em vermelho. |
| Etiqueta | cápsula tingida sem contorno, nunca quebra linha. Cor só para estado. |
| Estado vazio | símbolo grande e calado, título, o que fazer. |

## 10. Movimento

- Curvas: **mola** `cubic-bezier(.32,.72,0,1)` (folha, segmentado) e **padrão**
  `cubic-bezier(.25,.1,.25,1)`. 150 ms em estado, 300 ms em deslocamento.
- `prefers-reduced-motion` desliga tudo.
- Nada de animação de entrada em cada seção: a tela troca, não encena.

## 11. Acessibilidade

- Contraste AA em todo texto, inclusive o terciário.
- Foco visível só pelo teclado (`:focus-visible`), com halo do tint.
- Controle sem texto tem `aria-label`; segmentado usa `aria-pressed`;
  interruptor, `role="switch"` + `aria-checked`.
- Funciona com o texto no maior tamanho do iPhone e com zoom de 200%.

## 12. Checklist de tela nova

1. Título grande e, no admin, barra de ferramentas.
2. Só tokens: `grep "#[0-9a-fA-F]\{6\}"` fora dos blocos de token, vazio.
3. Conferir no claro **e** no escuro.
4. App: conferir em 390×844 (iPhone 14/15) e 375×667 (SE). Admin: 1366×768.
5. Nenhum `confirm(` nem `alert(`.
