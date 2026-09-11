#!/usr/bin/env python3
"""Build a source release containing only deployable code and documentation."""
from pathlib import Path
import hashlib
import json
import zipfile
root=Path(__file__).resolve().parents[1]
files=['Dockerfile','package.json','package-lock.json','tailwind.config.js','storage_backend.py','render.yaml','app.py','wsgi.py','requirements.txt','README.md','DEPLOYMENT.md','deploy_pythonanywhere.py','migrate_db.py']
for folder in ['templates','migrations','scripts','docs']:
    files.extend(str(path.relative_to(root)) for path in (root/folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.html','.sql','.py','.sh','.md'})
files.extend(['static/app.css','static/app.js','static/src/app.css'])
for name in files:
    if not (root/name).is_file(): raise SystemExit(f'Missing release file: {name}')
out=root/'output/releases'; out.mkdir(parents=True,exist_ok=True)
target=out/'halubilo-1.1.0.zip'
manifest={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sorted(files)}
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(files): archive.write(root/name,name)
    archive.writestr('release-manifest.json',json.dumps(manifest,indent=2))
print(f'Release: {target}')
print(f'SHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}')
print(f'{len(files)} files; no secrets, credentials, databases, uploads, or test data included.')
