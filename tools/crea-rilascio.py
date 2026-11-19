#!/usr/bin/env python3
"""Crea kit, cloud-init e ZIP studenti usando elenchi espliciti di file."""
import gzip
import hashlib
import io
from pathlib import Path
import re
import sys
import tarfile
import zipfile

from pubblicazione import ROOT, RUNTIME_FILES, STUDENT_FILES, verifica

REPOSITORY = 'tommasinigiovanni/24orebs-ai-builder-kit'


def archivio(versione):
    raw = io.BytesIO()
    entries = [('agenti-kit/' + name, (ROOT/name).read_bytes(), 0o755 if name.startswith('bin/') or name == 'install.sh' else 0o644) for name in RUNTIME_FILES]
    entries.append(('agenti-kit/VERSIONE', (versione+'\n').encode(), 0o644))
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.GNU_FORMAT) as archive:
        for name, content, mode in sorted(entries):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = mode
            info.mtime = 1767225600
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            archive.addfile(info, io.BytesIO(content))
    return gzip.compress(raw.getvalue(), mtime=0)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'v\d+\.\d+(\.\d+)?(-[a-z0-9]+)?', sys.argv[1]):
        raise SystemExit('Uso: python3 tools/crea-rilascio.py v1.3')
    verifica()
    version = sys.argv[1]
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    name = f'24orebs-ai-builder-kit-{version}.tar.gz'
    content = archivio(version)
    digest = hashlib.sha256(content).hexdigest()
    (dist/name).write_bytes(content)
    (dist/(name+'.sha256')).write_text(f'{digest}  {name}\n')
    text = (ROOT/'tools/cloud-init.modello.yaml').read_text().replace('{VERSIONE}',version).replace('{IMPRONTA}',digest).replace('{REPOSITORY}',REPOSITORY)
    if '{' in text or len(text.encode()) > 32*1024:
        raise ValueError('Cloud-init incompleto o oltre 32 KiB')
    (ROOT/'cloud-init.yaml').write_text(text)
    (dist/f'cloud-init-{version}.yaml').write_text(text)
    with zipfile.ZipFile(dist/f'guide-studenti-{version}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in STUDENT_FILES:
            info = zipfile.ZipInfo(path, date_time=(2026,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT/path).read_bytes())
    print(f'Archivio: {dist/name}\nSHA256: {digest}\nCloud-init: dist/cloud-init-{version}.yaml\nZIP studenti: dist/guide-studenti-{version}.zip')


if __name__ == '__main__':
    main()
