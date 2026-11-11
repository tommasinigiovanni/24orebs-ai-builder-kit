import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pubblicazione', ROOT/'tools/pubblicazione.py')
pubblicazione = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pubblicazione)


class PublicFilesTest(unittest.TestCase):
    def test_repository_matches_explicit_list(self):
        self.assertTrue(pubblicazione.verifica())

    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for path in pubblicazione.RUNTIME_FILES:
                target = root/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text('esempio')
            (root/'REGIA.md').write_text('materiale docente')
            with self.assertRaisesRegex(ValueError,'REGIA.md'):
                pubblicazione.verifica(root)

if __name__ == '__main__':
    unittest.main()
