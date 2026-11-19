# AI Builder da PC a server

Questa guida accompagna il profilo 24ORE del kit. Il percorso normale parte
dal terminale del tuo computer ed entra direttamente nella VM via SSH.

## Prima della lezione

- Attiva e verifica l’account Hetzner, compreso il metodo di pagamento.
- Tieni pronto l’account Claude che userai nel corso.
- Su Windows verifica che `ssh` e `ssh-keygen` siano disponibili in PowerShell. Se mancano, installa **Client OpenSSH** dalle funzionalità facoltative di Windows; il server OpenSSH sul PC non serve.
- Tieni disponibile un’app di autenticazione per attivare la dashboard.

## Crea la chiave sul Mac

Apri **Terminale** sul Mac. La chiave del corso si chiamerà `ai_builder`, per
tenerla distinta dalle eventuali chiavi già presenti.

```bash
mkdir -p "$HOME/.ssh"
ssh-keygen -t ed25519 -f "$HOME/.ssh/ai_builder" -C "ai-builder"
```

Se il programma dice che il file esiste già e chiede di sovrascriverlo,
rispondi **n**: riusa la chiave esistente se ne conosci la passphrase.
Se scegli una passphrase, annotala nel tuo gestore di password: protegge la
chiave sul Mac ed è distinta dalla password di un server.

Copia la **chiave pubblica** negli appunti:

```bash
pbcopy < "$HOME/.ssh/ai_builder.pub"
```

Il file `ai_builder` resta sul Mac. Su Hetzner incollerai solo il contenuto
del file con estensione `.pub`.

## Crea la chiave su Windows

Apri **PowerShell** sul tuo PC, senza bisogno di avviarlo come amministratore.

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\ai_builder" -C "ai-builder"
```

Se chiede di sovrascrivere un file esistente, rispondi **n**. La passphrase
protegge la chiave sul tuo computer; non è una password da impostare sulla VM.

Copia la **chiave pubblica** negli appunti:

```powershell
Get-Content "$env:USERPROFILE\.ssh\ai_builder.pub" | Set-Clipboard
```

Il file `ai_builder` resta sul PC. Su Hetzner incollerai solo la chiave pubblica.

## Entra in Hetzner: chiave e firewall

Il firewall si crea prima della VM, così la macchina nasce già protetta.

1. Nel progetto Hetzner apri la sezione delle chiavi SSH, aggiungi la chiave copiata e chiamala per esempio `PC corso`.
2. Apri la sezione **Firewalls** e crea un firewall nuovo. Chiamalo per esempio `ai-builder`.
3. Nelle regole in ingresso lascia solo queste tre: TCP **2222** per SSH, preferibilmente dal tuo IP, e TCP **80 e 443** da Internet per HTTPS e certificato della dashboard. Se il modulo propone altre regole, per esempio la porta 22, toglile: su questa VM SSH risponde sulla 2222.
4. Crea il firewall. Per ora non è agganciato a nessun server: lo selezioni nel prossimo passaggio, quando crei la VM.

## Crea la VM su Hetzner

1. Crea un server con immagine ufficiale **Ubuntu 24.04**. Per la prima prova usiamo questa versione; evita immagini personalizzate o snapshot.
2. Seleziona la tua chiave nella sezione **SSH keys**.
3. Nel campo **cloud-init** incolla il contenuto del file `cloud-init-v1.2.yaml` fornito dal docente. Usa il file della release AI Builder indicata dal docente.
4. Nella sezione dei firewall seleziona quello che hai appena creato. Un firewall che non è selezionato qui non protegge la VM.
5. Attiva il backup del fornitore se previsto per la tua esercitazione e crea il server. Hetzner fattura le risorse finché esistono, anche se il server è spento.
6. Annota l’IPv4 pubblico e attendi l’installazione: vedere la VM accesa non significa che cloud-init abbia terminato.

Non devi incollare la chiave una seconda volta nel cloud-init: il kit
autorizza per `agente` le chiavi pubbliche che Hetzner ha inserito per `root`.

## Entra direttamente via SSH

Sostituisci **IP** con l’IPv4 della tua VM. Sul Mac:

```bash
ssh -i "$HOME/.ssh/ai_builder" -o IdentitiesOnly=yes -p 2222 agente@IP
```

Su Windows, in PowerShell:

```powershell
ssh -i "$env:USERPROFILE\.ssh\ai_builder" -o IdentitiesOnly=yes -p 2222 agente@IP
```

Al primo collegamento verifica l’impronta del server con il docente, poi
conferma. Può essere chiesta la passphrase della chiave; non viene richiesta
una password SSH della VM. Se nei primi minuti il collegamento non riesce,
attendi e riprova sulla 2222: il kit potrebbe essere ancora in installazione.

Gli stessi comandi con `root@IP` al posto di `agente@IP` aprono l’account
amministrativo. Nel corso lavoriamo come **agente**, anche per Claude e tmux.

## Controlla il completamento e fai il login

I prossimi comandi si scrivono **nella VM**, dopo il collegamento SSH.

```bash
sudo cloud-init status --wait
cat /var/lib/agenti-kit/stato
whoami
sudo -n whoami
claude auth login
```

`whoami` deve rispondere `agente`; il comando con `sudo` deve rispondere
`root`. Nel file di stato i passi devono essere `ok`. Durante il login Claude
apri sul tuo PC il link mostrato nel terminale e completa l’autorizzazione.

`salute` aiuta a vedere cosa manca: prima del login, dell’apertura di una
sessione e dell’attivazione della dashboard è normale che segnali quei passi.

## Apri una sessione che resta sulla VM

```bash
tmux new -s boss
cd ~/boss
claude -n boss --rc
```

Con `--rc` la stessa sessione compare anche su Claude desktop e nell’app
Claude sul telefono, con il tuo account: è il boss che gira sulla VM, visto
da un’altra finestra.

Per uscire da tmux lasciando aperta la sessione premi **Ctrl+B**, rilascia,
poi premi **D**. Ora puoi chiudere il collegamento con `exit` e chiudere il PC.
Quando rientri in SSH:

```bash
tmux attach -t boss
```

tmux mantiene la sessione quando chiudi SSH. Il programma può comunque
aspettare una tua conferma. Un riavvio della VM chiude i processi: in quel
caso riapri tmux e riprendi la conversazione con `claude -r boss --rc`.

## Attiva la dashboard già installata

Da SSH, come `agente`, **fuori dalla schermata di Claude**, esegui:

```bash
plancia-attiva
```

Scegli una password della dashboard di almeno 12 caratteri e confermala.
Il comando mostra un codice di attivazione valido 15 minuti e l’indirizzo
HTTPS della tua dashboard. Aprilo nel browser, entra come **admin**, usa la
password scelta e il codice di attivazione, quindi collega l’app di
autenticazione e conserva i codici di recupero. Se il codice scade prima
dell’attivazione, rilancia `plancia-attiva` per prepararne uno nuovo.

Password e secondo fattore della dashboard sono separati dalla chiave SSH.
Il comando non reimposta un secondo fattore già attivo.

## Esegui il primo flusso pronto

Il kit ha già copiato un progetto con **dati fittizi**, per avere un esempio
comune prima di adattarlo al proprio lavoro.

```bash
cd ~/progetti/report-settimanale
python3 riepilogo.py
cat uscite/riepilogo.md
```

Risultato iniziale: **5 attività**, di cui **3 aperte**, **1 in corso** e
**1 completata**; **2 priorità alte ancora da chiudere**. Questo programma
non usa un modello AI: è l’opzione pronta da eseguire, controllare e poi
modificare con Claude. Per lavorarci con Claude apri una nuova sessione:

```bash
tmux new -s report -c ~/progetti/report-settimanale
claude -n report
```

## Porta la tua cartella sulla VM

Sulla VM non serve tutto il computer: basta la cartella del lavoro che vuoi
far andare avanti quando il PC è spento. Prima di copiarla togli quello che
non puoi dare a Claude, per esempio audio di riunioni e dati di clienti: un
file che non puoi dare a Claude non va nemmeno sulla VM.

I prossimi comandi si scrivono **nel terminale del tuo computer**, non nella
VM. Se sei ancora collegato, apri una seconda finestra. Sostituisci **IP** e
il percorso della cartella. In `scp` la porta si indica con la `-P` maiuscola.

Sul Mac:

```bash
scp -i "$HOME/.ssh/ai_builder" -o IdentitiesOnly=yes -P 2222 -r "$HOME/Documents/NOME" agente@IP:progetti/
```

Su Windows, in PowerShell:

```powershell
scp -i "$env:USERPROFILE\.ssh\ai_builder" -o IdentitiesOnly=yes -P 2222 -r "$env:USERPROFILE\Documents\NOME" agente@IP:progetti/
```

La cartella arriva in `~/progetti/` sulla VM, con lo stesso nome. Rientra in
SSH, controlla che ci sia e apri una sessione al suo interno:

```bash
ls ~/progetti
tmux new -s sistema -c ~/progetti/NOME
claude -n sistema
```

Alla prima apertura in una cartella nuova Claude chiede se ti fidi di quella
cartella. È la tua: conferma.

Chiedi a Claude: «Che istruzioni trovi in questa cartella? Cosa ti serve per
lavorare che qui non c’è?». I programmi installati sul tuo computer non
viaggiano con la cartella: la VM ha i suoi.

È una copia: da ora le cartelle sono due. Una modifica fatta sul PC non
compare sulla VM finché non la copi di nuovo. Rilanciando il comando, i file
con lo stesso nome sulla VM vengono sovrascritti.

## Fai partire un lavoro da solo

Da qui in avanti il lavoro sul sistema lo chiedi a Claude: tu dici cosa vuoi,
lui propone come farlo, tu leggi e dai l’ok.

Scegli il lavoro. Può essere quello della tua cartella, lo strumento che
pulisce i fogli visto nel modulo sui dati, oppure l’esempio pronto in
`~/progetti/report-settimanale`. Apri una sessione nella sua cartella.

Prima descrivi il lavoro in quattro parti: cosa deve fare, come ti consegna il
risultato, quando parte, cosa non deve mai fare. Scrivi a Claude, con le tue
risposte al posto di quelle dell’esempio:

```text
Scrivi nel CLAUDE.md di questa cartella queste quattro parti, e poi fammelo leggere.
COSA: prepari il riepilogo delle attività con il programma riepilogo.py.
COME: il risultato va nel file uscite/riepilogo.md.
QUANDO: ogni notte alle 2, come programma, senza una conversazione aperta. Per adesso lo lancio io.
LIMITI: leggi e scrivi solo in questa cartella, non cancelli niente, non usi sudo, non mandi niente fuori dalla macchina.
```

Leggi quello che propone. I limiti contano più del resto: un lavoro che parte
da solo non ha nessuno che legge i permessi.

Poi fallo girare una volta a mano:

```text
Fallo adesso, una volta, e dimmi cosa hai prodotto.
```

Apri il risultato e controllalo: che sia partito non basta. Se non ti torna,
correggi il `CLAUDE.md`, non il risultato. Quando ti torna bene tre volte di
fila, fallo partire da solo:

```text
Adesso fallo partire da solo ogni notte alle 2, come dice il CLAUDE.md. Prima dimmi come lo fai e aspetta il mio ok. Per provarlo fallo partire una volta fra due minuti.
```

Leggi il piano prima di dire ok. tmux tiene accesa una sessione; il timer che
Claude prepara fa partire un programma a un orario, anche senza sessioni
aperte. Sono due cose diverse.

Quando il lavoro è partito, controlla il risultato e non solo la partenza:

```text
Fammi vedere l'ultima esecuzione: quando è partita, com'è finita e dov'è il risultato.
```

Per fermarlo:

```text
Ferma il lavoro notturno e dimmi cosa hai spento.
```

Per l’esempio pronto il kit ha già un timer, spento: Claude lo trova e ti
propone di usarlo o di cambiargli orario.

## Attiva Telegram

Il gateway Telegram è già sulla VM, spento. Ti serve un bot tuo.

1. Su Telegram cerca **BotFather**, quello con la spunta blu. Scrivigli `/newbot` e scegli un nome e uno username. La riga lunga che ti risponde è il **token**: è la password del bot.
2. Da SSH, come `agente`, **fuori dalla schermata di Claude**, esegui:

```bash
telegram-attiva
```

3. Incolla il token quando lo chiede: mentre lo incolli non si vede. Il comando lo scrive in un file che leggi solo tu.
4. Apri Telegram e scrivi un messaggio qualsiasi al tuo bot. Il comando ti mostra chi ha scritto: se sei tu, rispondi `s`.
5. Su Telegram, nella chat del bot, scrivi `/aiuto`: ti dice cosa puoi chiedergli. Toccando `/` vedi i comandi: `/stato` elenca le sessioni accese, `/lavori` i lavori programmati, con la prossima partenza e l’esito dell’ultima volta.

Tre cose da sapere:

- **Il token non si incolla nella chat con Claude.** Quello che passa dalla conversazione resta nei suoi registri.
- **Il bot risponde solo a chi è nella lista.** Finché la lista è vuota non risponde a nessuno, ed è giusto così.
- **Da Telegram Claude legge e risponde.** Legge i file della cartella `progetti`, per esempio l’esito di un lavoro: puoi chiedergli com’è andata. Non cambia file, non lancia comandi e non legge la cartella `segreti`. Per intervenire si usa il boss.

## Fatti avvisare quando il lavoro finisce

Nella sessione del tuo progetto scrivi a Claude:

```text
Quando il lavoro della notte finisce, mandami un messaggio su Telegram con l'esito: com'è andata e se ci sono stati errori. Se fallisce voglio saperlo lo stesso. Prima dimmi cosa cambi e aspetta il mio ok.
```

Per provare che gli avvisi arrivano, da SSH:

```bash
avvisa "Prova dalla mia macchina"
```

## Se qualcosa non va

- **Connection refused o timeout:** verifica IP, completamento dell’installazione e firewall TCP 2222; la porta 22 non è quella del corso.
- **Permission denied (publickey):** verifica che `-i` indichi la chiave privata sul PC e che la corrispondente chiave pubblica sia stata selezionata alla creazione. Non caricare la chiave privata sulla VM.
- **scp cerca un file chiamato 2222:** hai scritto `-p` minuscola. In `scp` la porta vuole la `-P` maiuscola; in `ssh` resta minuscola.
- **La dashboard non si apre:** controlla di aver completato `plancia-attiva` e che nel firewall siano aperte le porte TCP 80 e 443. Poi chiedi a Claude: «La dashboard non si apre: controlla il servizio session-board e Caddy e dimmi perché».
- **Ctrl+B e D non funziona:** sono due gesti, non tre tasti insieme. Tieni premuto Ctrl, premi B, rilascia tutti e due, poi premi D. tmux risponde `detached`.
- **tmux risponde duplicate session:** non è un errore, la sessione con quel nome esiste già. Guardala con `tmux ls` e rientra con `tmux attach -t boss`.
- **Hai scritto exit dentro Claude:** quella sessione si è spenta. Da Claude non si esce: ci si stacca con Ctrl+B e D, e lui resta a lavorare. Riaprila con `claude -r boss --rc`.
- **Il bot non risponde:** controlla di essere nella lista rilanciando `telegram-attiva`. Se la lista è a posto, chiedi a Claude: «Il gateway Telegram non risponde: guarda il suo registro e dimmi perché».
- **avvisa dice che manca il token:** il bot non è ancora attivato. Lancia `telegram-attiva`.
- **tmux non trova boss dopo un riavvio:** crea una nuova sessione, entra in `~/boss` e usa `claude -r boss --rc`.
- **Il kit segnala da-completare:** leggi `sudo tail -n 60 /var/log/agenti-kit-install.log`. Il docente può rilanciarlo con `sudo bash /opt/agenti-kit/install.sh`; il profilo 24ORE viene ricordato.

## Riferimenti

- [Chiavi in Windows OpenSSH](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)
- [Generazione delle chiavi SSH](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
- [SSH su Hetzner](https://docs.hetzner.com/cloud/servers/getting-started/connecting-to-the-server/)
- [tmux](https://github.com/tmux/tmux/wiki/Getting-Started)
