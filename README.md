# AI Builder kit studenti

Kit e guide per il corso AI Builder di 24ORE Business School.

Il kit prepara una VM Ubuntu per lavorare con Claude Code: accesso SSH con
chiave sulla porta **2222**, utente **agente**, tmux e dashboard HTTPS.
La stessa chiave consente l’accesso come root; le operazioni quotidiane e
Claude lavorano come agente, con sudo disponibile per gli interventi
amministrativi e conferma prevista nelle impostazioni di Claude Code.

## Da dove iniziare

1. Segui la [guida Mac e Windows](guide/avvio-mac-windows.md) per creare la tua chiave SSH.
2. Su Hetzner crea un firewall con TCP 2222 per SSH, preferibilmente dal tuo IP, e TCP 80/443 per HTTPS.
3. Crea una VM Hetzner con immagine ufficiale Ubuntu 24.04, seleziona la chiave pubblica e il firewall appena creato, e incolla il [cloud-init](cloud-init.yaml).
4. Attendi l’installazione ed entra via SSH come agente. Completa il login Claude.
5. Esegui `plancia-attiva` nel terminale SSH per scegliere password della dashboard e attivare il secondo fattore.
6. Quando hai il tuo bot, esegui `telegram-attiva` per collegare Telegram: il token si incolla nel terminale, senza mostrarlo.

La chiave privata rimane sul tuo computer. Il cloud-init non contiene
credenziali personali e scarica il kit da una release pubblica con SHA256
verificato. Non occorre un account GitHub per scaricarlo sulla VM.

Per i primi concetti: [schema PC, SSH, tmux e server](guide/pc-server-tmux.png).

## Cosa trovi sulla macchina

- Claude Code, tmux, Git e i comandi `aiuto` e `salute`.
- Account agente con le chiavi pubbliche selezionate in Hetzner e accesso root con la stessa chiave. Autenticazione SSH con password disabilitata.
- Dashboard portable v1.2, verificata con SHA256, eseguita come agente e raggiungibile via Caddy all’indirizzo `https://IP-con-trattini.sslip.io`.
- Un esempio già eseguibile in `~/progetti/report-settimanale`, con dati fittizi e risultato verificabile. Il timer è predisposto ma spento.
- Un gateway Telegram già copiato in `~/progetti/telegram`, spento: risponde solo alle chat della tua lista. Dal telefono vedi le sessioni accese e i lavori programmati, e puoi chiedere a Claude cosa c’è nei tuoi progetti: legge, non cambia file e non lancia comandi. Il comando `avvisa "testo"` manda un messaggio dalla macchina al telefono.
- Codex e Syncthing disponibili come strumenti facoltativi del kit.

Password e secondo fattore della dashboard si attivano personalmente dopo
l’installazione. Il modello Claude richiede il proprio account; l’esempio
Python pronto non chiama modelli AI a ogni esecuzione. Il token di Telegram lo
inserisci tu al momento dell’attivazione: il kit non contiene credenziali.
Hindsight non fa parte di questa versione.

## Download

La [release v1.2](https://github.com/tommasinigiovanni/24orebs-ai-builder-kit/releases/tag/v1.2)
contiene archivio del kit, impronta SHA256, cloud-init e ZIP con le guide per
gli studenti. Il kit è destinato a VM nuove. La v1.1 è stata provata su una VM
Hetzner nuova, con un bot Telegram vero e un riavvio. La v1.2 corregge quello
che quella prova ha trovato e rende il bot più usabile: ha superato le prove
automatiche del repository, e il suo gateway è stato provato su quella stessa
VM.

## Verifiche e compilazione della release

```bash
python3 tools/pubblicazione.py
python3 -m unittest discover -s test -p 'test_*.py' -v
python3 tools/crea-rilascio.py v1.2
```

I controlli verificano l’elenco dei file pubblicabili e il contenuto degli
archivi. La CI prova anche accesso SSH reale root/agente, rifiuto password e
chiavi estranee, sudo, sessione tmux dopo disconnessione, seconda installazione,
esempio programmabile, gateway Telegram copiato e spento, servizio dashboard
come agente. Il gateway è provato con Telegram e Claude simulati.
