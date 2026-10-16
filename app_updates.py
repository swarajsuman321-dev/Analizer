"""GitHub release updates: bounded network reads, hash verification and rollback."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit

REPOSITORY='swarajsuman321-dev/Analizer'
RELEASES=f'https://github.com/{REPOSITORY}/releases'
MANIFEST_URL=RELEASES+'/latest/download/update.json'
MAX_DOWNLOAD=600*1024*1024


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise ValueError('Invalid stable release version')
    return tuple(map(int,value.split('.')))


def validate_manifest(data):
    if not isinstance(data,dict):raise ValueError('Invalid update information')
    version_tuple(data.get('version'))
    expected=RELEASES+f"/download/v{data['version']}/ApplianceSignalStudio.exe"
    if data.get('url')!=expected:raise ValueError('Unexpected update download location')
    if not re.fullmatch('[0-9a-f]{64}',str(data.get('sha256',''))):raise ValueError('Missing update checksum')
    if type(data.get('size')) is not int or not 0<data['size']<=MAX_DOWNLOAD:raise ValueError('Invalid update size')
    return data


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ApplianceSignalStudio-Updater'}),timeout=30)


def check_latest():
    with request(MANIFEST_URL) as response:
        data=response.read(256*1024+1)
    if len(data)>256*1024:raise ValueError('Update information is too large')
    return validate_manifest(json.loads(data))


def download_update(manifest,directory,progress=lambda value:None):
    manifest=validate_manifest(manifest);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    target=directory/f"ApplianceSignalStudio-{manifest['version']}.exe";part=target.with_suffix('.part')
    digest=hashlib.sha256();size=0
    try:
        with request(manifest['url']) as response,part.open('wb') as stream:
            if urlsplit(response.geturl()).scheme!='https':raise ValueError('Update requires HTTPS')
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>manifest['size']:raise ValueError('Update is larger than expected')
                stream.write(chunk);digest.update(chunk);progress(int(size*100/manifest['size']))
        if size!=manifest['size'] or digest.hexdigest()!=manifest['sha256']:raise ValueError('Update verification failed; the current app is unchanged')
        os.replace(part,target);return target
    finally:
        part.unlink(missing_ok=True)


def ps_quote(value):return "'"+str(value).replace("'","''")+"'"


def launch_installer(download,recovery,directory,expected_hash):
    if sys.platform!='win32' or not getattr(sys,'frozen',False):raise ValueError('Automatic installation is available in the downloaded Windows app')
    with Path(download).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected_hash:raise ValueError('The downloaded update changed; download it again')
    target=Path(sys.executable).resolve();backup=target.with_suffix('.previous.exe')
    # Check write access before asking the app to exit. No elevation or shell interpolation.
    try:
        with tempfile.TemporaryFile(dir=target.parent):pass
    except OSError as exc:raise ValueError('Move the app to a writable folder before installing an update') from exc
    script=Path(directory)/'install-update.ps1'
    script.write_text(f'''$ErrorActionPreference = 'Stop'
$target = {ps_quote(target)}
$backup = {ps_quote(backup)}
$download = {ps_quote(download)}
$recovery = {ps_quote(recovery)}
$log = {ps_quote(Path(directory)/'install.log')}
Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
try {{
    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne {ps_quote(expected_hash)}) {{ throw 'Update checksum changed' }}
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $target -Destination $backup
    try {{
        Move-Item -LiteralPath $download -Destination $target
        Start-Process -FilePath $target -ArgumentList @('--restore', ('"' + $recovery + '"'))
    }} catch {{
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $backup -Destination $target
        Start-Process -FilePath $target -ArgumentList @('--restore', ('"' + $recovery + '"'))
        throw
    }}
}} catch {{ $_ | Out-File -LiteralPath $log }}
''',encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True)
