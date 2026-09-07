# Agente de controle de acesso — Roma Tênis

Roda num mini-PC na quadra, na mesma rede dos leitores faciais. É a ponte entre
o servidor (que está na nuvem) e os equipamentos.

## Por que existe

Os leitores ficam na rede local, com IP tipo `192.168.1.108`. A VPS está na
nuvem e **não tem rota** até esse IP. As três saídas possíveis eram:

| caminho | por quê não / por quê sim |
|---|---|
| Expor o leitor na internet | ❌ Nunca. Um controlador de acesso com porta aberta é um convite: quem entrar abre o portão. |
| VPN da quadra até a VPS | Funciona, mas o servidor passa a depender da internet da quadra estar de pé no instante exato de cada liberação. |
| **Agente local** | ✅ O leitor nunca sai da rede local. Se a internet cair, quem já foi sincronizado continua entrando. |

## Como funciona

A cada 20 segundos o agente:

1. busca no servidor o estado desejado — quem pode entrar e em que janelas;
2. reconcilia cada leitor com esse estado;
3. recolhe as passagens registradas;
4. devolve tudo num relatório;
5. executa comandos pontuais (abrir o portão pelo painel).

Duas decisões que valem entender antes de mexer:

**O servidor manda o estado inteiro, não um diff.** Custa alguns KB por ciclo e
paga com robustez: se o agente ficar horas offline, se alguém apagar um usuário
na tela do leitor, ou se um leitor for trocado, o ciclo seguinte conserta
sozinho.

**A janela de horário é aplicada ligando e desligando a pessoa no leitor**, não
pelo período de validade do equipamento. O leitor guarda um intervalo só por
usuário, e um associado pode ter três jogos na mesma semana.

## Hardware

- Mini-PC ou Raspberry Pi 4 na quadra, com rede cabeada até o switch dos leitores
- Python 3.11+
- Dois leitores: um de entrada, um de saída (SS 3531 MF LITE)

## Instalação

```bash
sudo apt install python3 python3-venv
git clone <repo> /opt/roma-agente && cd /opt/roma-agente/agente-acesso
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

No painel do admin, aba **Acesso**:

1. cadastre os dois leitores (IP, porta, usuário e senha de cada um);
2. gere o token do agente e copie;
3. ajuste os minutos antes/depois e ligue o controle de acesso.

Teste um ciclo antes de instalar como serviço:

```bash
.venv/bin/python agente.py --url https://romatenis.com.br --token COLE_O_TOKEN --uma-vez
```

### Como serviço

`/etc/systemd/system/roma-agente.service`:

```ini
[Unit]
Description=Agente de acesso Roma Tenis
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/roma-agente/agente-acesso
Environment=ROMA_URL=https://romatenis.com.br
Environment=ROMA_TOKEN=cole_o_token_aqui
ExecStart=/opt/roma-agente/agente-acesso/.venv/bin/python agente.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now roma-agente
journalctl -u roma-agente -f
```

O painel mostra o agente como online quando ele reporta; cada leitor mostra o
último contato e o último erro.

## Antes de ligar no portão

- **Relógio dos leitores**: aponte o NTP dos dois para o mesmo servidor. O
  horário das passagens vem do equipamento; relógio errado embaralha o registro
  de quem entrou e quem saiu.
- **Anti-fake ligado** nos dois. Sem isso uma foto no celular abre o portão.
- **IP fixo** nos dois leitores (ou reserva por MAC no roteador). Se o IP mudar,
  o agente perde o equipamento até alguém corrigir no painel.
- **Trava magnética com mola**: o relé do leitor (DOOR_COM/DOOR_NO) aciona a
  trava. Confira se o portão fecha sozinho — a mola é o que garante que a
  liberação de uma pessoa não vira porta aberta.

## Testes

```bash
python teste_agente.py
```

Sobe os leitores em modo simulado (`DriverSimulado`) e verifica a parte difícil:
janela de horário, envio de foto só quando muda, limpeza de sobras, leitor fora
do ar, e a classificação de entrada/saída/negado. Não precisa de servidor nem de
hardware.

Para rodar o agente inteiro sem hardware, contra o servidor de verdade:

```bash
python agente.py --token COLE_O_TOKEN --simulado --uma-vez
```

## ⚠️ Endpoints ainda não confirmados

A linha de controle de acesso da Intelbras é derivada da plataforma Dahua e usa
CGI sobre HTTP com autenticação Digest. Os caminhos em `driver.py` (`_ROTAS`)
seguem essa convenção, **mas não foram verificados contra a documentação
oficial** — ela é liberada pela Intelbras sob solicitação, pelo chatbot (ver o
tutorial em `Acesso/Intelbras/`).

Quando a documentação chegar, ajustar `_ROTAS` e os formatos de payload em
`driver.py` é a única mudança necessária: nada fora desse arquivo depende do
dialeto do equipamento. Os testes e todo o resto do sistema continuam valendo.
