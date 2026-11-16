#!/usr/bin/env python3
"""Gateway fra Telegram e Claude, sulla tua macchina.

Riceve i messaggi che scrivi al tuo bot, li passa a Claude e ti rimanda la
risposta. Risponde solo alle chat scritte nella lista bianca: tutti gli altri
vengono ignorati.

È un punto di partenza, fatto per essere letto e cambiato. Usa solo la
libreria standard di Python: non c'è niente da installare.

Uso:
  python3 gateway.py --attiva     il primo avvio, guidato: chiede il token
                                  senza mostrarlo, riconosce il bot e mette
                                  la tua chat nella lista bianca. Sulla
                                  macchina del corso lo lancia telegram-attiva.
  python3 gateway.py --chi-sono   mostra il numero della chat di chi scrive
                                  al bot, senza rispondere.
  python3 gateway.py              avvia il gateway.
  python3 gateway.py --avvisa "testo"
                                  manda il testo alle chat private della
                                  lista bianca e finisce. Serve ai lavori
                                  che girano da soli, per dirti com'è andata.

File:
  ~/segreti/telegram.txt                   il token del bot, quello che ti dà
                                           BotFather. È un segreto: lo scrivi
                                           tu nel file, da SSH, non passa
                                           dalla conversazione.
  ~/.config/gateway-telegram/chat-ammesse  la lista bianca: un numero di chat
                                           per riga.

Comandi che puoi scrivere al bot:
  /stato    le sessioni accese sulla macchina
  /nuova    ricomincia la conversazione da capo
  tutto il resto va a Claude.

Telegram accetta un solo lettore per bot: un solo gateway acceso per volta.
L'avviso non legge, scrive soltanto: funziona anche mentre il gateway è acceso.
"""

import getpass
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIGURAZIONE = Path.home() / ".config" / "gateway-telegram"
# Il token sta con gli altri segreti della macchina, un file per servizio.
FILE_TOKEN = Path.home() / "segreti" / "telegram.txt"
FILE_CHAT = CONFIGURAZIONE / "chat-ammesse"
# La cartella dove lavora Claude quando gli scrivi da Telegram.
CARTELLA = Path(os.environ.get("GATEWAY_CARTELLA", Path.home() / "progetti" / "telegram"))
ATTESA_TELEGRAM = 50  # secondi: Telegram tiene aperta la richiesta finché non arriva un messaggio
TEMPO_MASSIMO_CLAUDE = 600  # secondi: oltre, la risposta si abbandona
LUNGHEZZA_MASSIMA = 4000  # Telegram accetta messaggi fino a 4096 caratteri
FORMA_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")  # numero del bot, due punti, chiave


def leggi_token():
    if not FILE_TOKEN.exists():
        sys.exit(f"Manca il file del token: {FILE_TOKEN}\n"
                 "Il bot non è ancora attivato. Entra in SSH come agente e lancia: telegram-attiva")
    permessi = stat.S_IMODE(FILE_TOKEN.stat().st_mode)
    if permessi & 0o077:
        sys.exit(f"Il file del token lo possono leggere anche altri. Chiudilo: chmod 600 {FILE_TOKEN}")
    token = FILE_TOKEN.read_text().strip()
    if not token:
        sys.exit(f"Il file del token è vuoto: {FILE_TOKEN}")
    return token


def leggi_chat_ammesse():
    """La lista bianca. Si rilegge a ogni messaggio: si cambia senza riavviare."""
    if not FILE_CHAT.exists():
        return set()
    ammesse = set()
    for riga in FILE_CHAT.read_text().splitlines():
        riga = riga.split("#")[0].strip()
        if riga.lstrip("-").isdigit():
            ammesse.add(int(riga))
    return ammesse


def chiama_telegram(token, metodo, parametri, attesa=30):
    """Chiama un metodo dell'API di Telegram e ne restituisce il risultato."""
    indirizzo = f"https://api.telegram.org/bot{token}/{metodo}"
    dati = urllib.parse.urlencode(parametri).encode()
    with urllib.request.urlopen(indirizzo, data=dati, timeout=attesa) as risposta:
        corpo = json.load(risposta)
    if not corpo.get("ok"):
        raise RuntimeError(f"Telegram ha risposto di no a {metodo}: {corpo.get('description')}")
    return corpo["result"]


def a_pezzi(testo):
    """Spezza un testo lungo in messaggi che Telegram accetta."""
    testo = testo.strip() or "(nessuna risposta)"
    pezzi = []
    while len(testo) > LUNGHEZZA_MASSIMA:
        taglio = testo.rfind("\n", 0, LUNGHEZZA_MASSIMA)
        if taglio <= 0:
            taglio = LUNGHEZZA_MASSIMA
        pezzi.append(testo[:taglio])
        testo = testo[taglio:].lstrip("\n")
    pezzi.append(testo)
    return pezzi


def chiedi_a_claude(testo, continua):
    """Passa il messaggio a Claude e ne restituisce la risposta.

    Claude viene lanciato con -p: risponde e si chiude. In questo modo può
    leggere i file della cartella, ma non cambia niente e non lancia comandi,
    perché nessuno è lì a dargli il permesso.
    """
    CARTELLA.mkdir(parents=True, exist_ok=True)
    comando = ["claude", "-p", testo]
    if continua:
        comando.append("--continue")
    try:
        esito = subprocess.run(comando, cwd=CARTELLA, capture_output=True, text=True,
                               timeout=TEMPO_MASSIMO_CLAUDE, check=False)
    except subprocess.TimeoutExpired:
        return "Claude ci sta mettendo troppo: ho lasciato perdere. Riprova con una richiesta più piccola."
    except FileNotFoundError:
        return "Sulla macchina non trovo il comando claude."
    if esito.returncode != 0:
        errore = (esito.stderr or esito.stdout).strip()
        return f"Claude si è fermato con un errore:\n{errore[-1500:]}"
    return esito.stdout


def stato_macchina():
    esito = subprocess.run(["tmux", "ls"], capture_output=True, text=True, check=False)
    if esito.returncode != 0:
        return "Nessuna sessione accesa."
    return "Sessioni accese:\n" + esito.stdout.strip()


def rispondi(token, chat, testo):
    for pezzo in a_pezzi(testo):
        chiama_telegram(token, "sendMessage", {"chat_id": chat, "text": pezzo})


def avvisa(token, testo):
    """Manda un avviso alle chat private della lista bianca. Dice a quante.

    È il messaggio che parte dalla macchina, senza che nessuno abbia scritto:
    lo lancia un lavoro quando finisce. Ai gruppi non va, come i comandi.
    """
    destinatari = sorted(numero for numero in leggi_chat_ammesse() if numero > 0)
    if not destinatari:
        sys.exit("Avviso non mandato: la lista bianca è vuota, non so a chi scrivere. "
                 f"Il tuo numero di chat va in {FILE_CHAT}")
    for numero in destinatari:
        rispondi(token, numero, testo)
    return len(destinatari)


def scrivi_token(token):
    """Scrive il token nel suo file, leggibile solo da chi lo possiede."""
    FILE_TOKEN.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descrittore = os.open(FILE_TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descrittore, "w") as file:
        file.write(token + "\n")
    os.chmod(FILE_TOKEN, 0o600)


def aggiungi_alla_lista(numero, nome):
    FILE_CHAT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(FILE_CHAT, "a") as file:
        file.write(f"{numero}  # {nome}\n")
    os.chmod(FILE_CHAT, 0o600)


def attiva(chiedi_segreto=getpass.getpass, chiedi=input, attesa_massima=180):
    """Il primo avvio, guidato. Il token si scrive qui, mai in una conversazione.

    Tre passi: il token, chiesto senza mostrarlo e scritto solo se Telegram
    lo riconosce; il nome del bot; la lista bianca, con la chat di chi scrive
    al bot per primo e conferma di essere il proprietario.
    """
    nuovo = not FILE_TOKEN.exists()
    if nuovo:
        print("Serve il token del tuo bot. Su Telegram cerca BotFather, quello con la\n"
              "spunta blu, scrivigli /newbot e segui i due passi: nome e username.\n"
              "La riga lunga che ti risponde è il token: è la password del bot.\n")
        token = chiedi_segreto("Incolla qui il token e premi Invio (mentre lo incolli non si vede): ").strip()
        if not FORMA_TOKEN.fullmatch(token):
            sys.exit("Quello che hai incollato non ha la forma di un token di Telegram.\n"
                     "Copialo di nuovo da BotFather, tutto intero, e rilancia telegram-attiva.")
    else:
        token = leggi_token()

    try:
        bot = chiama_telegram(token, "getMe", {})
    except urllib.error.HTTPError as errore:
        if errore.code in (401, 404):
            sys.exit("Telegram non riconosce questo token. Copialo di nuovo da BotFather e rilancia telegram-attiva.")
        sys.exit(f"Telegram ha risposto con l'errore {errore.code}. Riprova fra poco.")
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as errore:
        sys.exit(f"Non raggiungo Telegram ({type(errore).__name__}). Riprova fra poco.")
    if nuovo:
        scrivi_token(token)
    nome_bot = bot.get("username", "?")
    print(f"Bot riconosciuto: @{nome_bot}. Il token è nel file {FILE_TOKEN}, lo leggi solo tu.")

    if any(numero > 0 for numero in leggi_chat_ammesse()):
        print(f"La lista di chi può comandare è già scritta in {FILE_CHAT}: non la tocco.")
        return

    print(f"\nAdesso apri Telegram, cerca @{nome_bot} e scrivigli un messaggio qualsiasi.\n"
          f"Aspetto fino a {attesa_massima // 60} minuti...", flush=True)
    scadenza = time.monotonic() + attesa_massima
    prossimo = None
    while time.monotonic() < scadenza:
        parametri = {"timeout": 20, "allowed_updates": json.dumps(["message"])}
        if prossimo is not None:
            parametri["offset"] = prossimo
        try:
            in_arrivo = chiama_telegram(token, "getUpdates", parametri, attesa=35)
        except urllib.error.HTTPError as errore:
            if errore.code == 409:
                sys.exit("C'è già un lettore acceso per questo bot. Spegnilo e rilancia telegram-attiva.")
            sys.exit(f"Telegram ha risposto con l'errore {errore.code}. Riprova fra poco.")
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as errore:
            sys.exit(f"Non raggiungo Telegram ({type(errore).__name__}). Riprova fra poco.")
        for voce in in_arrivo:
            prossimo = voce["update_id"] + 1
            chat = (voce.get("message") or {}).get("chat", {})
            if chat.get("type") != "private":
                continue
            numero = chat.get("id")
            nome = chat.get("first_name") or "?"
            risposta = chiedi(f"Ha scritto {nome} (chat {numero}). Sei tu? [s/N] ").strip().lower()
            if risposta not in ("s", "si", "sì"):
                print("Lasciato fuori. Aspetto il tuo messaggio...", flush=True)
                continue
            aggiungi_alla_lista(numero, nome)
            # Il messaggio di prova si segna come letto: il gateway non lo passerà a Claude.
            chiama_telegram(token, "getUpdates", {"offset": prossimo, "timeout": 0})
            rispondi(token, numero, "Fatto: da adesso rispondo solo a te. Prova a scrivermi /stato")
            print(f"La chat {numero} è nella lista: il bot risponde solo a te.")
            return
    sys.exit("Non è arrivato nessun messaggio. Rilancia telegram-attiva quando hai Telegram aperto.")


def gestisci(token, messaggio, stato, chi_sono=False):
    """Decide cosa fare di un messaggio arrivato. Restituisce cosa ha fatto."""
    chat = messaggio.get("chat", {})
    numero = chat.get("id")
    testo = (messaggio.get("text") or "").strip()
    nome = chat.get("first_name") or chat.get("title") or "?"

    if chi_sono:
        print(f"Ha scritto la chat {numero} ({nome}, tipo {chat.get('type')})", flush=True)
        return "mostrato"

    # La lista bianca: solo chat private, e solo quelle scritte nel file.
    if chat.get("type") != "private" or numero not in leggi_chat_ammesse():
        print(f"Ignorato un messaggio dalla chat {numero} ({nome}): non è nella lista bianca",
              flush=True)
        return "ignorato"

    if not testo:
        rispondi(token, numero, "Per ora leggo solo i messaggi di testo.")
        return "non-testo"
    if testo == "/stato":
        rispondi(token, numero, stato_macchina())
        return "stato"
    if testo in ("/nuova", "/start"):
        stato["continua"] = False
        rispondi(token, numero, "Pronto. La prossima richiesta comincia una conversazione nuova.")
        return "nuova"

    chiama_telegram(token, "sendChatAction", {"chat_id": numero, "action": "typing"})
    risposta = chiedi_a_claude(testo, stato.get("continua", False))
    stato["continua"] = True
    rispondi(token, numero, risposta)
    return "claude"


def gira(token, chi_sono=False):
    stato = {"continua": False}
    prossimo = None
    print("Gateway acceso. Per fermarlo: Ctrl+C.", flush=True)
    while True:
        parametri = {"timeout": ATTESA_TELEGRAM, "allowed_updates": json.dumps(["message"])}
        if prossimo is not None:
            parametri["offset"] = prossimo
        try:
            novita = chiama_telegram(token, "getUpdates", parametri, attesa=ATTESA_TELEGRAM + 15)
        except urllib.error.HTTPError as errore:
            if errore.code == 409:
                sys.exit("C'è già un altro lettore acceso per questo bot. Spegnilo, poi riavvia.")
            if errore.code == 401:
                sys.exit("Telegram non riconosce il token. Controlla il file del token.")
            print(f"Telegram ha risposto con l'errore {errore.code}: riprovo fra poco.", flush=True)
            time.sleep(10)
            continue
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as errore:
            print(f"Non raggiungo Telegram ({errore}): riprovo fra poco.", flush=True)
            time.sleep(10)
            continue
        for voce in novita:
            prossimo = voce["update_id"] + 1
            messaggio = voce.get("message")
            if not messaggio:
                continue
            try:
                gestisci(token, messaggio, stato, chi_sono)
            except Exception as errore:  # un messaggio andato male non ferma il gateway
                print(f"Errore su un messaggio: {errore}", flush=True)


def main():
    argomenti = sys.argv[1:]
    if argomenti[:1] == ["--avvisa"]:
        if len(argomenti) != 2 or not argomenti[1].strip():
            sys.exit('Uso: python3 gateway.py --avvisa "testo del messaggio"')
        token = leggi_token()
        try:
            quante = avvisa(token, argomenti[1])
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as errore:
            # Il motivo si scrive senza l'indirizzo chiamato: dentro c'è il token.
            sys.exit(f"Avviso non mandato: Telegram non ha risposto ({type(errore).__name__}).")
        print(f"Avviso mandato a {quante} chat.")
        return
    if argomenti == ["--attiva"]:
        try:
            attiva()
        except (KeyboardInterrupt, EOFError):
            sys.exit("\nAttivazione interrotta: niente è stato acceso.")
        return
    if argomenti not in ([], ["--chi-sono"]):
        sys.exit(__doc__)
    token = leggi_token()
    try:
        gira(token, chi_sono=argomenti == ["--chi-sono"])
    except KeyboardInterrupt:
        print("\nGateway spento.")


if __name__ == "__main__":
    main()
