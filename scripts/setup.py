#!/usr/bin/env python3
"""Create local configuration once; never replace existing secrets."""
import os
import argparse
from pathlib import Path
import secrets
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rehearsal', action='store_true')
args = parser.parse_args()
target = root / ('.env.rehearsal' if args.rehearsal else '.env')
if target.exists():
    print(f'{target.name} already exists; left unchanged.')
else:
    data = (root / '.env.example').read_text().replace('SECRET_KEY=\n', f'SECRET_KEY={secrets.token_hex(32)}\n')
    if args.rehearsal:
        data = data.replace('PORT=8080', 'PORT=8081').replace('EVENT_NAME=Halubilo', 'EVENT_NAME=Halubilo rehearsal')
        data += f'REHEARSAL_ONLY=1\nREHEARSAL_PASSWORD={secrets.token_urlsafe(24)}\n'
    with target.open('x') as output:
        os.chmod(target, 0o600)
        output.write(data)
    print(f'Created private {target.name} with a unique secret.')
