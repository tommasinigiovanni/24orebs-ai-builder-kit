#!/usr/bin/env python3
"""Prove del gateway, senza Telegram e senza Claude: tutti e due sono finti.

Uso: python3 -m unittest discover -s test -p 'test_*.py'
"""

import contextlib
import io
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

        def telegram_finto(token, metodo, parametri, attesa=30):
            self.chiamate.append((metodo, parametri))
            return {}

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
        self.assertEqual(self.inviati(), ["risposta a: che ore sono?"])
        self.assertTrue(stato["continua"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
