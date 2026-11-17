#!/usr/bin/env python3
"""Prove del gateway, senza Telegram e senza Claude: tutti e due sono finti.

Uso: python3 -m unittest discover -s test -p 'test_*.py'
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "profili" / "telegram"))
import gateway  # noqa: E402


def messaggio(numero, testo, tipo="private"):
    return {"chat": {"id": numero, "type": tipo, "first_name": "Prova"}, "text": testo}


class ProvaGateway(unittest.TestCase):
    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        base = Path(self.cartella.name)
        self.file_chat = base / "chat-ammesse"
        self.file_token = base / "token"
        self.file_chat.write_text("# la mia chat\n111\n")
        self.chiamate = []
        self.richieste = []
        self.risposte_telegram = {}  # metodo -> cosa restituisce, o l'errore che solleva

        def telegram_finto(token, metodo, parametri, attesa=30):
            self.chiamate.append((metodo, parametri))
            esito = self.risposte_telegram.get(metodo, {})
            if isinstance(esito, Exception):
                raise esito
            return esito

        def claude_finto(testo, continua):
            self.richieste.append((testo, continua))
            return f"risposta a: {testo}"

        for bersaglio, valore in (
            ("FILE_CHAT", self.file_chat),
            ("FILE_TOKEN", self.file_token),
            ("chiama_telegram", telegram_finto),
            ("chiedi_a_claude", claude_finto),
        ):
            finto = mock.patch.object(gateway, bersaglio, valore)
            finto.start()
            self.addCleanup(finto.stop)
        self.addCleanup(self.cartella.cleanup)

    def inviati(self):
        return [p["text"] for m, p in self.chiamate if m == "sendMessage"]

    def test_chat_fuori_dalla_lista_ignorata(self):
        esito = gateway.gestisci("t", messaggio(999, "ciao"), {})
        self.assertEqual(esito, "ignorato")
        self.assertEqual(self.chiamate, [])
        self.assertEqual(self.richieste, [])

    def test_gruppo_ignorato_anche_se_in_lista(self):
        self.file_chat.write_text("-555\n")
        esito = gateway.gestisci("t", messaggio(-555, "ciao", tipo="group"), {})
        self.assertEqual(esito, "ignorato")
        self.assertEqual(self.richieste, [])

    def test_lista_vuota_non_risponde_a_nessuno(self):
        self.file_chat.unlink()
        self.assertEqual(gateway.gestisci("t", messaggio(111, "ciao"), {}), "ignorato")

    def test_chat_ammessa_va_a_claude(self):
        stato = {"continua": False}
        esito = gateway.gestisci("t", messaggio(111, "che ore sono?"), stato)
        self.assertEqual(esito, "claude")
        self.assertEqual(self.richieste, [("che ore sono?", False)])
        self.assertEqual(self.inviati(), [gateway.ATTESA, "risposta a: che ore sono?"])
        self.assertTrue(stato["continua"])

    def test_l_attesa_non_suona_e_sparisce_dopo_la_risposta(self):
        self.risposte_telegram["sendMessage"] = {"message_id": 77}
        gateway.gestisci("t", messaggio(111, "che ore sono?"), {})
        mandati = [p for m, p in self.chiamate if m == "sendMessage"]
        self.assertEqual(mandati[0], {"chat_id": 111, "text": gateway.ATTESA, "disable_notification": "true"})
        # La risposta è un messaggio nuovo e senza silenziatore: il telefono suona.
        self.assertEqual(mandati[1], {"chat_id": 111, "text": "risposta a: che ore sono?"})
        metodi = [m for m, _ in self.chiamate]
        self.assertEqual(metodi[-1], "deleteMessage")
        self.assertEqual(self.chiamate[-1][1], {"chat_id": 111, "message_id": 77})

    def test_se_l_attesa_non_si_toglie_la_risposta_e_arrivata_lo_stesso(self):
        self.risposte_telegram["sendMessage"] = {"message_id": 77}
        self.risposte_telegram["deleteMessage"] = RuntimeError("no")
        self.assertEqual(gateway.gestisci("t", messaggio(111, "che ore sono?"), {}), "claude")
        self.assertEqual(self.inviati(), [gateway.ATTESA, "risposta a: che ore sono?"])

    def test_start_e_aiuto_dicono_cosa_si_puo_chiedere(self):
        for testo in ("/start", "/aiuto", "/help"):
            self.chiamate.clear()
            self.assertEqual(gateway.gestisci("t", messaggio(111, testo), {}), "aiuto")
            for comando, _ in gateway.COMANDI:
                self.assertIn(f"/{comando}", self.inviati()[0])
        self.assertEqual(self.richieste, [])

    def test_comando_sconosciuto_non_va_a_claude(self):
        self.assertEqual(gateway.gestisci("t", messaggio(111, "/cancella tutto"), {}), "sconosciuto")
        self.assertEqual(self.richieste, [])
        self.assertIn("/cancella", self.inviati()[0])
        self.assertIn("/stato", self.inviati()[0])

    def test_comando_con_il_nome_del_bot(self):
        with mock.patch.object(gateway, "stato_macchina", lambda: "Nessuna sessione accesa."):
            self.assertEqual(gateway.gestisci("t", messaggio(111, "/STATO@prova_bot"), {}), "stato")

    def test_lavori_non_passa_da_claude(self):
        with mock.patch.object(gateway, "lavori_programmati", lambda: "Lavori programmati: 0"):
            self.assertEqual(gateway.gestisci("t", messaggio(111, "/lavori"), {}), "lavori")
        self.assertEqual(self.richieste, [])
        self.assertEqual(self.inviati(), ["Lavori programmati: 0"])

    def test_il_menu_dei_comandi_va_a_telegram(self):
        gateway.pubblica_comandi("t")
        metodo, parametri = self.chiamate[-1]
        self.assertEqual(metodo, "setMyCommands")
        elenco = json.loads(parametri["commands"])
        self.assertEqual([voce["command"] for voce in elenco], ["stato", "lavori", "nuova", "aiuto"])
        self.assertTrue(all(voce["description"] for voce in elenco))

    def test_secondo_messaggio_continua_la_conversazione(self):
        stato = {"continua": False}
        gateway.gestisci("t", messaggio(111, "uno"), stato)
        gateway.gestisci("t", messaggio(111, "due"), stato)
        self.assertEqual(self.richieste, [("uno", False), ("due", True)])

    def test_nuova_ricomincia(self):
        stato = {"continua": True}
        self.assertEqual(gateway.gestisci("t", messaggio(111, "/nuova"), stato), "nuova")
        gateway.gestisci("t", messaggio(111, "tre"), stato)
        self.assertEqual(self.richieste, [("tre", False)])

    def test_stato_non_passa_da_claude(self):
        with mock.patch.object(gateway, "stato_macchina", lambda: "Sessioni accese:\nboss"):
            self.assertEqual(gateway.gestisci("t", messaggio(111, "/stato"), {}), "stato")
        self.assertEqual(self.richieste, [])
        self.assertEqual(self.inviati(), ["Sessioni accese:\nboss"])

    def test_chi_sono_non_risponde_e_non_chiama_claude(self):
        esito = gateway.gestisci("t", messaggio(999, "ciao"), {}, chi_sono=True)
        self.assertEqual(esito, "mostrato")
        self.assertEqual(self.chiamate, [])
        self.assertEqual(self.richieste, [])

    def test_risposta_lunga_a_pezzi(self):
        lungo = "\n".join(f"riga {n} " + "x" * 80 for n in range(200))
        pezzi = gateway.a_pezzi(lungo)
        self.assertGreater(len(pezzi), 1)
        self.assertTrue(all(len(p) <= gateway.LUNGHEZZA_MASSIMA for p in pezzi))
        self.assertEqual("\n".join(pezzi), lungo)

    def test_token_leggibile_da_altri_rifiutato(self):
        self.file_token.write_text("123:abc\n")
        os.chmod(self.file_token, 0o644)
        with self.assertRaises(SystemExit):
            gateway.leggi_token()
        os.chmod(self.file_token, 0o600)
        self.assertEqual(gateway.leggi_token(), "123:abc")

    def test_token_mancante_rifiutato(self):
        with self.assertRaises(SystemExit):
            gateway.leggi_token()

    # L'avviso di fine lavoro: un messaggio che parte dalla macchina.

    def destinatari(self):
        return [p["chat_id"] for m, p in self.chiamate if m == "sendMessage"]

    def test_avviso_va_a_ogni_chat_privata_della_lista(self):
        self.file_chat.write_text("111\n222  # un collega\n")
        self.assertEqual(gateway.avvisa("t", "Pulizia finita: 3 file, 0 errori."), 2)
        self.assertEqual(sorted(self.destinatari()), [111, 222])
        self.assertEqual(set(self.inviati()), {"Pulizia finita: 3 file, 0 errori."})

    def test_avviso_non_legge_i_messaggi_del_bot(self):
        # Il gateway acceso è l'unico lettore del bot: l'avviso deve solo scrivere.
        gateway.avvisa("t", "finito")
        self.assertEqual({m for m, _ in self.chiamate}, {"sendMessage"})
        self.assertEqual(self.richieste, [])

    def test_avviso_non_va_ai_gruppi(self):
        self.file_chat.write_text("111\n-555\n")
        self.assertEqual(gateway.avvisa("t", "finito"), 1)
        self.assertEqual(self.destinatari(), [111])

    def test_avviso_con_lista_vuota_si_ferma_e_lo_dice(self):
        self.file_chat.unlink()
        with self.assertRaises(SystemExit) as uscita:
            gateway.avvisa("t", "finito")
        self.assertIn("lista bianca", str(uscita.exception.code))
        self.assertEqual(self.chiamate, [])

    def test_avviso_lungo_a_pezzi(self):
        lungo = "\n".join(f"riga {n} " + "x" * 80 for n in range(200))
        gateway.avvisa("t", lungo)
        self.assertGreater(len(self.inviati()), 1)
        self.assertTrue(all(len(p) <= gateway.LUNGHEZZA_MASSIMA for p in self.inviati()))

    def esegui_main(self, *argomenti):
        self.file_token.write_text("123:abc\n")
        os.chmod(self.file_token, 0o600)
        uscita = io.StringIO()
        with mock.patch.object(sys, "argv", ["gateway.py", *argomenti]), \
                mock.patch.object(gateway, "gira", side_effect=AssertionError("non deve restare acceso")), \
                contextlib.redirect_stdout(uscita):
            gateway.main()
        return uscita.getvalue()

    def test_main_avvisa_manda_e_finisce(self):
        uscita = self.esegui_main("--avvisa", "Pulizia finita.")
        self.assertEqual(self.inviati(), ["Pulizia finita."])
        self.assertIn("1 chat", uscita)

    def test_main_avvisa_senza_testo_mostra_l_uso(self):
        for argomenti in (["--avvisa"], ["--avvisa", "  "], ["--avvisa", "a", "b"]):
            with self.assertRaises(SystemExit) as uscita:
                self.esegui_main(*argomenti)
            self.assertIn("--avvisa", str(uscita.exception.code))
        self.assertEqual(self.chiamate, [])

    def test_main_avvisa_se_telegram_non_risponde_esce_con_errore(self):
        def telegram_spento(token, metodo, parametri, attesa=30):
            raise urllib.error.URLError("rete assente")

        with mock.patch.object(gateway, "chiama_telegram", telegram_spento):
            with self.assertRaises(SystemExit) as uscita:
                self.esegui_main("--avvisa", "finito")
        self.assertIn("Avviso non mandato", str(uscita.exception.code))
        self.assertNotIn("123:abc", str(uscita.exception.code))


TOKEN_BUONO = "123456789:" + "A" * 35


def novita(numero, nome="Giovanni", tipo="private", update=10):
    return {"update_id": update,
            "message": {"chat": {"id": numero, "type": tipo, "first_name": nome}, "text": "ciao"}}


class ProvaAttivazione(unittest.TestCase):
    """telegram-attiva: token dal terminale, bot riconosciuto, lista di chi comanda."""

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        base = Path(self.cartella.name)
        self.file_token = base / "segreti" / "telegram.txt"
        self.file_chat = base / "config" / "chat-ammesse"
        self.chiamate = []
        self.in_arrivo = []  # una lista di novità per ogni getUpdates
        self.errore_getme = None
        self.domande = []

        def telegram_finto(token, metodo, parametri, attesa=30):
            self.chiamate.append((metodo, dict(parametri)))
            if metodo == "getMe":
                if self.errore_getme:
                    raise self.errore_getme
                return {"username": "prova_bot"}
            if metodo == "getUpdates":
                return self.in_arrivo.pop(0) if self.in_arrivo else []
            return {}

        for bersaglio, valore in (("FILE_CHAT", self.file_chat), ("FILE_TOKEN", self.file_token),
                                  ("chiama_telegram", telegram_finto)):
            finto = mock.patch.object(gateway, bersaglio, valore)
            finto.start()
            self.addCleanup(finto.stop)
        self.addCleanup(self.cartella.cleanup)

    def attiva(self, token=TOKEN_BUONO, risposte=("s",), attesa=60):
        risposte = list(risposte)

        def chiedi(domanda):
            self.domande.append(domanda)
            return risposte.pop(0)

        uscita = io.StringIO()
        with contextlib.redirect_stdout(uscita):
            gateway.attiva(chiedi_segreto=lambda domanda: token, chiedi=chiedi, attesa_massima=attesa)
        return uscita.getvalue()

    def metodi(self):
        return [m for m, _ in self.chiamate]

    def test_primo_avvio_scrive_token_e_lista(self):
        self.in_arrivo = [[novita(111)]]
        uscita = self.attiva()
        self.assertEqual(self.file_token.read_text().strip(), TOKEN_BUONO)
        self.assertEqual(os.stat(self.file_token).st_mode & 0o777, 0o600)
        self.assertEqual(gateway.leggi_chat_ammesse(), {111})
        self.assertIn("@prova_bot", uscita)
        self.assertNotIn(TOKEN_BUONO, uscita)
        # Il messaggio di prova si segna come letto: il gateway non lo passerà a Claude.
        self.assertIn(("getUpdates", {"offset": 11, "timeout": 0}), self.chiamate)
        self.assertEqual([p["chat_id"] for m, p in self.chiamate if m == "sendMessage"], [111])

    def test_token_senza_forma_non_viene_scritto_ne_provato(self):
        with self.assertRaises(SystemExit) as uscita:
            self.attiva(token="ciao")
        self.assertFalse(self.file_token.exists())
        self.assertEqual(self.chiamate, [])
        self.assertNotIn("ciao", str(uscita.exception.code))

    def test_token_rifiutato_da_telegram_non_viene_scritto(self):
        self.errore_getme = urllib.error.HTTPError("https://api.telegram.org/botSEGRETO/getMe",
                                                   401, "Unauthorized", None, None)
        with self.assertRaises(SystemExit) as uscita:
            self.attiva()
        self.assertFalse(self.file_token.exists())
        self.assertNotIn(TOKEN_BUONO, str(uscita.exception.code))
        self.assertNotIn("SEGRETO", str(uscita.exception.code))

    def test_chi_non_viene_riconosciuto_resta_fuori(self):
        self.in_arrivo = [[novita(999, nome="Estraneo", update=10)], [novita(111, update=11)]]
        self.attiva(risposte=("n", "s"))
        self.assertEqual(gateway.leggi_chat_ammesse(), {111})
        self.assertEqual(len(self.domande), 2)

    def test_i_gruppi_non_entrano_nella_lista(self):
        self.in_arrivo = [[novita(-555, tipo="group", update=10)], [novita(111, update=11)]]
        self.attiva()
        self.assertEqual(gateway.leggi_chat_ammesse(), {111})
        self.assertEqual(len(self.domande), 1)

    def test_token_gia_presente_non_viene_richiesto(self):
        self.file_token.parent.mkdir(parents=True)
        self.file_token.write_text(TOKEN_BUONO + "\n")
        os.chmod(self.file_token, 0o600)
        self.in_arrivo = [[novita(111)]]

        def non_chiedere(domanda):
            raise AssertionError("il token c'è già")

        with contextlib.redirect_stdout(io.StringIO()):
            gateway.attiva(chiedi_segreto=non_chiedere, chiedi=lambda d: "s", attesa_massima=60)
        self.assertEqual(gateway.leggi_chat_ammesse(), {111})

    def test_lista_gia_scritta_non_viene_toccata(self):
        self.file_chat.parent.mkdir(parents=True)
        self.file_chat.write_text("111\n")
        self.attiva()
        self.assertNotIn("getUpdates", self.metodi())
        self.assertEqual(self.file_chat.read_text(), "111\n")

    def test_nessun_messaggio_si_ferma_senza_scrivere_la_lista(self):
        with self.assertRaises(SystemExit):
            self.attiva(attesa=0)
        self.assertEqual(gateway.leggi_chat_ammesse(), set())
        # Il token buono resta: al secondo giro non va incollato di nuovo.
        self.assertTrue(self.file_token.exists())

    def test_i_messaggi_arrivati_durante_la_conferma_si_segnano_letti(self):
        # Telegram manda /start appena si apre il bot; chi poi scrive anche
        # "ciao" mentre il terminale chiede "Sei tu?" lascia un messaggio in
        # coda. Senza questa pulizia il gateway lo passava a Claude.
        self.in_arrivo = [[novita(111, update=10)], [novita(111, update=11)],
                          [novita(111, update=12)], []]
        self.attiva()
        letture = [p for m, p in self.chiamate if m == "getUpdates" and p.get("timeout") == 0]
        self.assertEqual([p["offset"] for p in letture], [11, 12, 13])
        self.assertEqual(gateway.leggi_chat_ammesse(), {111})


class ProvaStato(unittest.TestCase):
    """/stato e /lavori: cosa legge il gateway dalla macchina."""

    def comando_finto(self, codice, uscita=""):
        return mock.patch.object(gateway.subprocess, "run",
                                 return_value=mock.Mock(returncode=codice, stdout=uscita, stderr=""))

    def test_stato_elenca_le_sessioni_per_nome(self):
        with self.comando_finto(0, "boss\nsistema\n"):
            self.assertEqual(gateway.stato_macchina(), "Sessioni accese: 2\n- boss\n- sistema")

    def test_stato_senza_sessioni(self):
        with self.comando_finto(1):
            self.assertEqual(gateway.stato_macchina(), "Nessuna sessione accesa.")

    def test_proprieta_legge_le_righe_di_systemd(self):
        with self.comando_finto(0, "ActiveState=active\nNextElapseUSecRealtime=Wed 2026-11-18 08:30:00 UTC\n") as lancio:
            valori = gateway.proprieta("pulizia.timer", "ActiveState", "NextElapseUSecRealtime")
        self.assertEqual(valori["ActiveState"], "active")
        self.assertEqual(gateway.quando(valori["NextElapseUSecRealtime"]), "2026-11-18 08:30")
        self.assertEqual(lancio.call_args.args[0][:4], ["systemctl", "--user", "show", "pulizia.timer"])

    def test_quando_senza_data_resta_vuoto(self):
        self.assertEqual(gateway.quando(""), "")
        self.assertEqual(gateway.quando("n/a"), "")

    def lavori(self, nomi, risposte):
        with tempfile.TemporaryDirectory() as cartella:
            for nome in nomi:
                (Path(cartella) / f"{nome}.timer").write_text("")
            (Path(cartella) / "altro.service").write_text("")
            with mock.patch.object(gateway, "LAVORI", Path(cartella)), \
                 mock.patch.object(gateway, "proprieta", lambda unita, *nomi: risposte.get(unita, {})):
                return gateway.lavori_programmati()

    def test_lavori_acceso_e_riuscito(self):
        testo = self.lavori(["pulizia"], {
            "pulizia.timer": {"ActiveState": "active", "Unit": "pulizia.service",
                              "NextElapseUSecRealtime": "Wed 2026-11-18 02:00:00 UTC"},
            "pulizia.service": {"Result": "success", "ExecMainExitTimestamp": "Tue 2026-11-17 02:00:09 UTC"}})
        self.assertEqual(testo, "Lavori programmati: 1\n- pulizia: acceso, prossima partenza 2026-11-18 02:00. "
                                "Ultima volta 2026-11-17 02:00: riuscito")

    def test_lavori_fallito_si_vede(self):
        testo = self.lavori(["pulizia"], {
            "pulizia.timer": {"ActiveState": "active", "Unit": "pulizia.service"},
            "pulizia.service": {"Result": "exit-code", "ExecMainExitTimestamp": "Tue 2026-11-17 02:00:09 UTC"}})
        self.assertIn("fallito", testo)
        self.assertNotIn("riuscito", testo)

    def test_lavori_spento_e_mai_partito(self):
        testo = self.lavori(["report-corso"], {"report-corso.timer": {"ActiveState": "inactive"}})
        self.assertIn("report-corso: spento, non parte da solo", testo)
        self.assertIn("Non è ancora partito", testo)

    def test_lavori_nessuno(self):
        self.assertIn("Nessun lavoro programmato", self.lavori([], {}))

    def test_lavori_senza_la_cartella(self):
        with mock.patch.object(gateway, "LAVORI", Path("/cartella/che/non/esiste")):
            self.assertIn("Nessun lavoro programmato", gateway.lavori_programmati())


class ProvaClaude(unittest.TestCase):
    """Cosa torna a Telegram quando Claude non può rispondere."""

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        finto = mock.patch.object(gateway, "CARTELLA", Path(self.cartella.name))
        finto.start()
        self.addCleanup(finto.stop)
        self.addCleanup(self.cartella.cleanup)

    def chiedi(self, codice, uscita="", errore=""):
        esito = mock.Mock(returncode=codice, stdout=uscita, stderr=errore)
        with mock.patch.object(gateway.subprocess, "run", return_value=esito):
            return gateway.chiedi_a_claude("ciao", False)

    def test_senza_login_dice_cosa_fare(self):
        risposta = self.chiedi(1, uscita="Not logged in · Please run /login")
        self.assertIn("claude auth login", risposta)
        self.assertNotIn("/login", risposta.replace("claude auth login", ""))

    def test_un_altro_errore_resta_leggibile(self):
        risposta = self.chiedi(1, errore="disco pieno")
        self.assertIn("disco pieno", risposta)

    def test_risposta_buona_passa_intera(self):
        self.assertEqual(self.chiedi(0, uscita="eccomi"), "eccomi")

    def test_claude_parte_senza_connettori_e_con_il_testo_semplice(self):
        esito = mock.Mock(returncode=0, stdout="eccomi", stderr="")
        with mock.patch.object(gateway.subprocess, "run", return_value=esito) as lancio:
            gateway.chiedi_a_claude("ciao", True)
        comando = lancio.call_args.args[0]
        self.assertEqual(comando[:2], ["claude", "-p"])
        # Il testo passa dall'ingresso, non dalla riga di comando.
        self.assertNotIn("ciao", comando)
        self.assertEqual(lancio.call_args.kwargs["input"], "ciao")
        self.assertIn("--continue", comando)
        istruzioni = comando[comando.index("--append-system-prompt") + 1]
        self.assertIn("Markdown", istruzioni)
        # Da Telegram solo strumenti di lettura, sui progetti, e mai sui segreti.
        self.assertEqual(comando[comando.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(comando[comando.index("--add-dir") + 1], str(gateway.LETTURA))
        self.assertEqual(comando[comando.index("--disallowedTools") + 1], "Read(~/segreti/**)")
        for vietato in ("Bash", "Edit", "Write"):
            self.assertNotIn(vietato, comando[comando.index("--tools") + 1])
        # I connettori dell'account claude.ai restano fuori dal canale Telegram.
        self.assertEqual(lancio.call_args.kwargs["env"]["ENABLE_CLAUDEAI_MCP_SERVERS"], "false")


if __name__ == "__main__":
    unittest.main(verbosity=2)
