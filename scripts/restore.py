#!/usr/bin/env python3
"""Validate and restore a backup into a NEW, offline data directory."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import closing


def restore(archive_path, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if any(path.name != 'uploads' or not path.is_dir() or any(path.iterdir()) for path in destination.iterdir()):
        raise ValueError('Destination must be empty. Restore into a new directory/volume; never overwrite live event data.')
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(names) != len(set(names)) or len(names) > 10005:
            raise ValueError('Duplicate or excessive archive entries.')
        if sum(item.file_size for item in entries) > 100 * 1024 * 1024:
            raise ValueError('Backup exceeds the 100 MiB restore limit.')
        if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > 2 * 1024 * 1024:
            raise ValueError('Missing or oversized manifest.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema') != 1:
            raise ValueError('Unsupported backup schema.')
        hashes = manifest.get('sha256', {})
        if set(hashes) != set(names) - {'manifest.json'} or 'scoresheet.db' not in hashes:
            raise ValueError('Manifest does not match archive contents.')
        data = {}
        for name, expected in hashes.items():
            if name != 'scoresheet.db' and not re.fullmatch(r'uploads/[a-f0-9]{32}\.jpg', name):
                raise ValueError('Unsafe or unexpected backup path.')
            contents = archive.read(name)
            if hashlib.sha256(contents).hexdigest() != expected:
                raise ValueError(f'Checksum mismatch: {name}')
            data[name] = contents
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=destination) as folder:
        staged = Path(folder)
        for name, contents in data.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
            target.chmod(0o600)
        (staged / 'uploads').mkdir(exist_ok=True)
        with closing(sqlite3.connect(staged / 'scoresheet.db')) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed.')
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Database has invalid references.')
            if connection.execute('SELECT version FROM schema_version').fetchall() != [(1,)]:
                raise ValueError('Database schema does not match manifest.')
            if connection.execute('SELECT COUNT(*) FROM event_state WHERE id=1').fetchone()[0] != 1:
                raise ValueError('Missing event state.')
            if connection.execute('SELECT COUNT(*) FROM score s JOIN activity a ON a.id=s.activity_id WHERE s.score<0 OR s.score>a.max_score').fetchone()[0]:
                raise ValueError('Database contains invalid scores.')
            if connection.execute('SELECT team_id,activity_id FROM score GROUP BY team_id,activity_id HAVING COUNT(*)>1').fetchall():
                raise ValueError('Database contains duplicate scores.')
            images = {f'uploads/{row[0]}' for row in connection.execute('SELECT image_filename FROM team WHERE image_filename IS NOT NULL')}
            if images != set(data) - {'scoresheet.db'}:
                raise ValueError('Database image references do not match the archive.')
            counts = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ['team', 'activity', 'score', 'audit', 'user']}
            # Normalize the offline copy for both local disk and PythonAnywhere.
            # WAL is a persistent database setting, not just an app environment flag.
            if connection.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise ValueError('Could not normalize database journaling for portable recovery.')
        # These final moves are safe only into the new, offline directory checked above.
        if (destination / 'uploads').exists():
            (destination / 'uploads').rmdir()
        os.replace(staged / 'uploads', destination / 'uploads')
        os.replace(staged / 'scoresheet.db', destination / 'scoresheet.db')
    return {'restored': str(destination), 'backup_created_at': manifest['created_at'], 'counts': counts}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('destination')
    args = parser.parse_args()
    try:
        archive = args.archive
        if archive == '-':
            contents = sys.stdin.buffer.read(100 * 1024 * 1024 + 1)
            if len(contents) > 100 * 1024 * 1024:
                raise ValueError('Backup archive exceeds 100 MiB.')
            archive = io.BytesIO(contents)
        print(json.dumps(restore(archive, args.destination), indent=2))
    except (ValueError, OSError, KeyError, sqlite3.Error, zipfile.BadZipFile) as error:
        parser.exit(1, f'Restore refused: {error}\n')
