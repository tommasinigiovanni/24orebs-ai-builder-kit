#!/usr/bin/env python3
"""Elenco esplicito dei file ammessi nel repository pubblico e nei download."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    'install.sh', 'bin/aiuto', 'bin/salute', 'bin/installa', 'bin/plancia-attiva',
    'bin/qr-login-claude', 'bin/qr-login-codex', 'boss/CLAUDE.md', 'boss/AGENTS.md',
    'console/bash_profile', 'macchina/ISTRUZIONI.md', 'profili/24ore.sh',
    'profili/chiavi_ssh.py', 'profili/session-board-24ore.service',
    'profili/report-corso.service', 'profili/report-corso.timer',
    'profili/esempio-24ore/CLAUDE.md', 'profili/esempio-24ore/STATO.md',
    'profili/esempio-24ore/attivita.csv', 'profili/esempio-24ore/riepilogo.py',
)
STUDENT_FILES = ('README.md', 'guide/avvio-mac-windows.md', 'guide/pc-server-tmux.png', 'cloud-init.yaml')
PUBLIC_FILES = frozenset(RUNTIME_FILES + STUDENT_FILES + (
    '.gitignore', '.github/workflows/controlli.yml', '.github/workflows/24ore.yml',
    'tools/crea-rilascio.py', 'tools/cloud-init.modello.yaml', 'tools/pubblicazione.py',
    'test/test_chiavi_ssh.py', 'test/test_pubblicazione.py', 'test/prova-24ore.sh',
))


def verifica(root=ROOT):
    found = set()
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in ('.git', 'dist', '__pycache__') for part in relative.parts) or path.name == '.DS_Store':
            continue
        if path.is_symlink():
            raise ValueError(f'Collegamento simbolico non ammesso: {relative}')
        if path.is_file():
            found.add(relative.as_posix())
    if (root / '.git').exists():
        # Controlla anche eventuali file tracciati in cartelle ignorate.
        found.update(subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines())
    unexpected = sorted(found - PUBLIC_FILES)
    if unexpected:
        raise ValueError('File fuori dall’elenco pubblico: ' + ', '.join(unexpected))
    missing = sorted(set(RUNTIME_FILES) - found)
    if missing:
        raise ValueError('File del kit mancanti: ' + ', '.join(missing))
    return found


if __name__ == '__main__':
    try:
        print(f'Controllo pubblico superato: {len(verifica())} file ammessi.')
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
