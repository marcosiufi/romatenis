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

**Quem impõe o horário é o leitor, não o agente.** Cada usuário tem uma validade
(`ValidFrom`/`ValidTo`) e o equipamento a respeita sozinho — se o agente cair no
meio de um jogo, o acesso ainda fecha na hora certa. O leitor guarda um intervalo
só por usuário e um associado pode ter três jogos na semana, então o agente
mantém essa validade apontando para a janela que vale (a em curso, ou a próxima)
e avança conforme cada uma termina.

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

- **Relógio dos leitores**: o agente aponta o NTP sozinho a cada execução
  (`a.ntp.br`). Confira no log do primeiro ciclo que não houve aviso de falha —
  o horário das passagens vem do equipamento, e relógio errado embaralha o
  registro de quem entrou e quem saiu.
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
janela em curso, avanço para a janela seguinte, bloqueio sem jogo, foto só quando
muda, limpeza de sobras sem apagar cadastro manual, leitor fora do ar, NTP uma
vez por leitor, classificação de entrada/saída/negado, e a leitura das respostas
do equipamento nos dois formatos documentados (JSON e `chave=valor`). Não precisa
de servidor nem de hardware.

Para rodar o agente inteiro sem hardware, contra o servidor de verdade:

```bash
python agente.py --token COLE_O_TOKEN --simulado --uma-vez
```

## API do equipamento

Endpoints conferidos contra a **coleção Postman oficial da Intelbras**
("Controle de Acesso - Bio-T") e o **Portal de Integração da Linha de Faciais**,
que confirma o SS 3531 MF como suportado.

- Autenticação **Digest** (RFC 2617)
- Resposta: `chave=valor` multilinha, JSON, ou a palavra `OK`
- A coleção convive com duas gerações de API. Onde há escolha, o driver usa a
  **V2** (`AccessUser.cgi`, `AccessFace.cgi`), que usa `UserID` como
  identificador em vez do `recno` interno — o `recno` muda quando o registro é
  reescrito, e amarrar nossa credencial a ele seria frágil.

| o que | chamada |
|---|---|
| testar | `GET /cgi-bin/magicBox.cgi?action=getSoftwareVersion` |
| criar usuário | `POST /cgi-bin/AccessUser.cgi?action=insertMulti` |
| mudar validade | `POST /cgi-bin/AccessUser.cgi?action=updateMulti` |
| consultar | `GET /cgi-bin/AccessUser.cgi?action=list&UserIDList[0]=…` |
| remover | `GET /cgi-bin/AccessUser.cgi?action=removeMulti&UserIDList[0]=…` |
| enviar face | `POST /cgi-bin/AccessFace.cgi?action=insertMulti` |
| passagens | `GET /cgi-bin/recordFinder.cgi?action=find&name=AccessControlCardRec&StartTime=<epoch>` |
| abrir porta | `GET /cgi-bin/accessControl.cgi?action=openDoor&channel=1&Type=Remote` |
| NTP | `GET /cgi-bin/configManager.cgi?action=setConfig&NTP.Address=…&NTP.Enable=true` |

### Melhoria possível: modo online

O equipamento sabe **empurrar** eventos para um servidor, em vez de ser
consultado (`Intelbras_ModeCfg.DeviceMode=2` + `PictureHttpUpload`). Daria
passagem em tempo real no painel, no lugar dos 20 s de hoje. Não foi
implementado: exigiria o agente subir um servidor HTTP e a consulta atual já
atende. Fica registrado como caminho, se um dia o tempo de reação importar.
