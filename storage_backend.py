"""Immutable team images, locally or in a server-only Supabase bucket."""
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app


class StorageError(RuntimeError):
    pass


def object_name(name):
    if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name):
        raise ValueError('Invalid image name.')
    return name


def remote_request(method, name, data=None):
    config = current_app.config
    url = f"{config['SUPABASE_URL'].rstrip('/')}/storage/v1/object"
    if method == 'GET':
        url += '/authenticated'
    url += f"/{config['SUPABASE_STORAGE_BUCKET']}/{object_name(name)}"
    key = config['SUPABASE_SERVICE_ROLE_KEY']
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'image/jpeg'}
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            result = response.read(2 * 1024 * 1024 + 1)
            if len(result) > 2 * 1024 * 1024:
                raise StorageError('Stored image exceeds the size limit.')
            return result
    except (HTTPError, URLError, TimeoutError, OSError):
        # Never expose credentials, provider error bodies, or signed URLs.
        raise StorageError('Image storage is unavailable. Check storage configuration and retry.') from None


def put_image(name, contents):
    object_name(name)
    if current_app.config['STORAGE_BACKEND'] == 'supabase':
        remote_request('POST', name, contents)
    else:
        (Path(current_app.config['UPLOAD_FOLDER']) / name).write_bytes(contents)


def get_image(name):
    object_name(name)
    if current_app.config['STORAGE_BACKEND'] == 'supabase':
        return remote_request('GET', name)
    try:
        return (Path(current_app.config['UPLOAD_FOLDER']) / name).read_bytes()
    except OSError:
        raise StorageError('A team image is missing. Repair it before creating a backup.') from None


def cleanup_image(name):
    # Remote writes cannot participate in the SQL transaction. Unreferenced UUID
    # objects are harmless; never delete on uncertain DB commit outcomes.
    if current_app.config['STORAGE_BACKEND'] == 'local':
        (Path(current_app.config['UPLOAD_FOLDER']) / object_name(name)).unlink(missing_ok=True)
