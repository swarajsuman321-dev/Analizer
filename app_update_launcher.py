"""Verified, edition-specific Windows update transactions.

PowerShell outlives the closing frozen application. All paths are quoted as
literal arguments; the old runtime and the recovery snapshot remain available
until and after the actual new workbench acknowledges restoration.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import subprocess
import sys
import tempfile
import zipfile

from app_update_transaction import atomic_json, create_request, file_hash

MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 30000


def stage_folder(archive, parent, expected_hash):
    """Extract only a bounded, complete runtime; reject Windows path aliases."""
    from app_operation_context import checkpoint
    archive, parent = Path(archive), Path(parent)
    checkpoint('Verifying the complete standalone runtime')
    if file_hash(archive) != expected_hash:
        raise ValueError('The downloaded ZIP changed; download it again')
    destination = Path(tempfile.mkdtemp(prefix='.signalstudio-stage-', dir=parent))
    inventory = {}
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('The update ZIP exceeds runtime size limits')
            seen = set()
            for entry in infos:
                checkpoint('Staging standalone runtime', len(seen), len(infos))
                name = entry.filename
                path = PurePosixPath(name)
                if ('\\' in name or '\x00' in name or path.is_absolute()
                        or '..' in path.parts or len(path.parts) < 2
                        or path.parts[0] != 'ApplianceSignalStudio'
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('Unsafe update ZIP path: ' + name)
                parts = path.parts[1:]
                if any(':' in part or part.endswith(('.', ' ')) or part.upper().split('.')[0] in
                       {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
                       for part in parts):
                    raise ValueError('Ambiguous Windows ZIP path: ' + name)
                if parts[0] not in ('ApplianceSignalStudio.exe', '_internal'):
                    raise ValueError('Unexpected runtime ZIP payload: ' + name)
                normalized = '/'.join(parts).casefold()
                if normalized in seen:
                    raise ValueError('Duplicate update ZIP path: ' + name)
                seen.add(normalized)
                target = destination.joinpath(*parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, target.open('xb') as output:
                    while chunk := source.read(1024 * 1024):
                        checkpoint()
                        output.write(chunk)
                inventory[str(target.relative_to(destination))] = file_hash(target)
        if (not (destination/'ApplianceSignalStudio.exe').is_file()
                or not any(path.startswith('_internal' + os.sep) for path in inventory)):
            raise ValueError('Update ZIP is missing the executable or bundled runtime')
        atomic_json(destination/'runtime-inventory.json', inventory)
        return destination
    except Exception:
        import shutil
        shutil.rmtree(destination)
        raise


def common_script(request, value, directory, parent_pids):
    from app_updates import ps_quote as q
    wait_pids = ','.join(str(int(pid)) for pid in parent_pids)
    return f'''$ErrorActionPreference = 'Stop'
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
Get-ChildItem Env: | Where-Object {{ $_.Name -like '_PYI_*' -or $_.Name -eq '_MEIPASS2' }} | ForEach-Object {{ Remove-Item -LiteralPath ('Env:' + $_.Name) }}
$requestPath = {q(request)}
$request = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$target = {q(value['executable'])}
$recovery = {q(value['recovery'])}
$fallbackRecovery = {q(value['fallback_recovery'])}
$log = {q(Path(directory)/'transaction.json')}
$launched = $null
$acknowledgedPid = $null
function Write-Outcome($status, $detail) {{
    @{{status=$status; error=$detail; target=$target; recovery=$recovery; fallback_recovery=$fallbackRecovery; request=$requestPath; previous=$previous; edition={q(value['kind'])}}} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $log -Encoding UTF8
}}
function Get-Sha256($path) {{
    $stream = [System.IO.File]::OpenRead($path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {{ return [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }}
    finally {{ $stream.Dispose(); $sha.Dispose() }}
}}
function Stop-FailedRuntime {{
    if ($null -ne $launched) {{
        $launched.Refresh()
        if (-not $launched.HasExited) {{ & taskkill.exe /PID $launched.Id /T /F | Out-Null }}
    }}
    # Onefile bootloaders own a separate child. If its parent has already
    # exited, still stop the exact acknowledging runtime before rollback.
    if ($null -ne $acknowledgedPid) {{
        $ackProcess = Get-Process -Id $acknowledgedPid -ErrorAction SilentlyContinue
        if ($null -ne $ackProcess -and $ackProcess.Path -eq $target) {{
            & taskkill.exe /PID $acknowledgedPid /T /F | Out-Null
        }}
    }}
}}
function Start-AndConfirm {{
    $script:launched = Start-Process -FilePath $target -ArgumentList @('--restore', ('"' + $recovery + '"'), '--update-request', ('"' + $requestPath + '"')) -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    while ([DateTime]::UtcNow -lt $deadline) {{
        if (Test-Path -LiteralPath $request.ack -PathType Leaf) {{
            $ack = Get-Content -LiteralPath $request.ack -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($ack.token -ne $request.token -or $ack.version -ne $request.version -or $ack.executable -ne $target -or $ack.recovery -ne $recovery) {{ throw 'Unexpected runtime acknowledgement' }}
            $script:acknowledgedPid = $ack.pid
            if ($ack.status -ne 'ready') {{ throw ('Workspace restore failed: ' + $ack.error) }}
            foreach ($item in $request.files.PSObject.Properties) {{
                if ($ack.files.($item.Name) -ne $item.Value -or (Get-Sha256 $item.Name) -ne $item.Value) {{ throw 'Recovery snapshot changed' }}
            }}
            # Allow a late import/event-loop failure to surface after the first
            # heartbeat. The application has already shown and restored state.
            Start-Sleep -Seconds 3
            $launched.Refresh()
            if ($launched.HasExited) {{ throw 'Updated application exited after restoring the workspace' }}
            $live = Get-Process -Id $ack.pid -ErrorAction Stop
            if ($live.Path -ne $target) {{ throw 'Acknowledgement process does not match the new runtime' }}
            Write-Outcome 'ready' ''
            return
        }}
        $launched.Refresh()
        if ($launched.HasExited) {{ throw ('Updated runtime exited before startup acknowledgement: ' + $launched.ExitCode) }}
        Start-Sleep -Milliseconds 200
    }}
    throw 'Timed out waiting for the updated application to restore the recovery workspace'
}}
Wait-Process -Id @({wait_pids}) -ErrorAction SilentlyContinue
'''


def launch_transaction(download, recovery, directory, manifest, *, parent_pid=None):
    from app_installation import installed_root
    from app_operation_context import checkpoint, mark_committed
    from app_updates import ps_quote as q, restart_environment, validate_manifest
    manifest = validate_manifest(manifest)
    checkpoint('Preparing an edition-specific update transaction')
    kind = manifest.get('kind', 'portable')
    previous = Path(sys.executable).resolve()
    if kind == 'installer':
        install = installed_root()
        if not install:
            raise ValueError('Setup updates are available only in the installed edition')
        target = install/'versions'/manifest['version']/'ApplianceSignalStudio.exe'
    else:
        target = previous
    # Preflight every writable destination before the old application closes.
    destination = install / 'versions' if kind == 'installer' else previous.parent
    try:
        with tempfile.TemporaryFile(dir=destination):
            pass
    except OSError as exc:
        action = 'Repair the per-user installation' if kind=='installer' else 'Move the standalone application to a writable folder'
        raise ValueError(f'{action} before updating. The runtime destination is not writable: {destination}') from exc
    directory = Path(directory)/'transactions'/secrets.token_hex(12)
    directory.mkdir(parents=True)
    request, value = create_request(directory, target, recovery, manifest['version'], kind)
    recovery = Path(value['recovery'])
    backup = previous.with_suffix('.previous.exe') if kind == 'portable' else previous.parent/('.signalstudio-recovery-'+directory.name)
    # Never overwrite an existing recovery runtime, including a different
    # edition's backup. Subsequent transactions use an independent directory.
    if kind == 'portable' and backup.exists():
        backup = directory/'ApplianceSignalStudio.previous.exe'
    staged = stage_folder(download, previous.parent, manifest['sha256']) if kind == 'portable-zip' else None
    lock_name = 'Local\\ApplianceSignalStudio.Update.' + hashlib.sha256(str(previous).casefold().encode('utf-8')).hexdigest()
    from app_update_transaction import update_wait_pids
    wait_pids = update_wait_pids() if parent_pid is None else [parent_pid]
    script = common_script(request, value, directory, wait_pids)
    script += f'''$download = {q(download)}
$previous = {q(previous)}
$backup = {q(backup)}
$switched = $false
$lock = $null
$lockHeld = $false
Write-Outcome 'waiting' ''
try {{
    # Isolate concurrent updates to this runtime; other editions are independent.
    $lock = [System.Threading.Mutex]::new($false, {q(lock_name)})
    try {{ $lockHeld = $lock.WaitOne(0) }} catch [System.Threading.AbandonedMutexException] {{ $lockHeld = $true }}
    if (-not $lockHeld) {{
        Write-Outcome 'blocked-concurrent' 'Another update is already running for this application folder; use its relaunched application or the recovery script.'
        return
    }}
    if ((Get-Sha256 $previous) -ne {q(file_hash(previous))}) {{ throw 'This application changed while waiting; open the current version before updating' }}
    if ((Get-Sha256 $download) -ne {q(manifest['sha256'])}) {{ throw 'Update checksum changed' }}
'''
    if kind == 'installer':
        script += f'''    $arguments = @('/SILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART', {q('/DIR="'+str(install)+'"')}, {q('/LOG="'+str(directory/'setup-install.log')+'"')})
    $setup = Start-Process -FilePath $download -ArgumentList $arguments -Wait -PassThru
    if ($setup.ExitCode -ne 0) {{ throw ('Setup failed with exit code ' + $setup.ExitCode) }}
'''
    elif kind == 'portable-zip':
        script += f'''    $staged = {q(staged)}
    if ((Get-Sha256 (Join-Path $staged 'runtime-inventory.json')) -ne {q(file_hash(staged/'runtime-inventory.json'))}) {{ throw 'Staged runtime inventory changed' }}
    $inventory = Get-Content -LiteralPath (Join-Path $staged 'runtime-inventory.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $actualFiles = @(Get-ChildItem -LiteralPath $staged -File -Recurse -Force | Where-Object {{ $_.FullName -ne (Join-Path $staged 'runtime-inventory.json') }})
    if ($actualFiles.Count -ne @($inventory.PSObject.Properties).Count) {{ throw 'Staged runtime contains unexpected files' }}
    foreach ($item in $inventory.PSObject.Properties) {{
        if ((Get-Sha256 (Join-Path $staged $item.Name)) -ne $item.Value) {{ throw 'Staged runtime checksum changed' }}
    }}
    New-Item -ItemType Directory -Path $backup | Out-Null
    # Move only app-owned executable/dependencies. Source recordings, outputs,
    # templates and every unowned adjacent file remain in their original place.
    Move-Item -LiteralPath $previous -Destination (Join-Path $backup 'ApplianceSignalStudio.exe')
    $switched = $true
    Move-Item -LiteralPath (Join-Path (Split-Path $previous) '_internal') -Destination (Join-Path $backup '_internal')
    Move-Item -LiteralPath (Join-Path $staged '_internal') -Destination (Join-Path (Split-Path $target) '_internal')
    Move-Item -LiteralPath (Join-Path $staged 'ApplianceSignalStudio.exe') -Destination $target
'''
    else:
        script += '''    Move-Item -LiteralPath $target -Destination $backup
    $switched = $true
    Copy-Item -LiteralPath $download -Destination $target
'''
    script += '''    Start-AndConfirm
} catch {
    $detail = $_.Exception.Message
    Write-Outcome 'rollback-in-progress' $detail
    Stop-FailedRuntime
'''
    if kind == 'portable':
        script += '''    if ($switched) {
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $backup -Destination $target
    }
'''
    elif kind == 'portable-zip':
        script += '''    if ($switched) {
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath (Join-Path $backup '_internal')) {
            $failed = Join-Path $backup 'failed-new-internal'
            if (Test-Path -LiteralPath (Join-Path (Split-Path $target) '_internal')) {
                Move-Item -LiteralPath (Join-Path (Split-Path $target) '_internal') -Destination $failed
            }
            Move-Item -LiteralPath (Join-Path $backup '_internal') -Destination (Join-Path (Split-Path $target) '_internal')
        }
        Move-Item -LiteralPath (Join-Path $backup 'ApplianceSignalStudio.exe') -Destination $target
    }
'''
    script += '''    Start-Process -FilePath $previous -ArgumentList @('--restore', ('"' + $fallbackRecovery + '"'))
    Write-Outcome 'recovered-previous' $detail
} finally {
    if ($lockHeld) { $lock.ReleaseMutex() }
    if ($null -ne $lock) { $lock.Dispose() }
}
'''
    name = 'install-setup-update.ps1' if kind == 'installer' else 'install-update.ps1'
    path = directory/name
    path.write_text(script, encoding='utf-8-sig')
    # Recovery after power loss or an externally terminated updater must not
    # depend on importing Python or launching a partially switched runtime.
    manual = f'''$ErrorActionPreference = 'Stop'
$target = {q(previous)}
$backup = {q(backup)}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
'''
    if kind=='portable':
        manual += '''if (Test-Path -LiteralPath $backup -PathType Leaf) {
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination ($target + '.failed-' + $stamp) }
    Move-Item -LiteralPath $backup -Destination $target
}
'''
    elif kind=='portable-zip':
        manual += '''if (Test-Path -LiteralPath (Join-Path $backup 'ApplianceSignalStudio.exe') -PathType Leaf) {
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination ($target + '.failed-' + $stamp) }
    $internal = Join-Path (Split-Path $target) '_internal'
    if (Test-Path -LiteralPath (Join-Path $backup '_internal')) {
        if (Test-Path -LiteralPath $internal) { Move-Item -LiteralPath $internal -Destination ($internal + '.failed-' + $stamp) }
        Move-Item -LiteralPath (Join-Path $backup '_internal') -Destination $internal
    }
    Move-Item -LiteralPath (Join-Path $backup 'ApplianceSignalStudio.exe') -Destination $target
}
'''
    manual += f'''$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
Get-ChildItem Env: | Where-Object {{ $_.Name -like '_PYI_*' -or $_.Name -eq '_MEIPASS2' }} | ForEach-Object {{ Remove-Item -LiteralPath ('Env:' + $_.Name) }}
Start-Process -FilePath $target -ArgumentList @('--restore', {q('"'+value['fallback_recovery']+'"')})
'''
    (directory/'recover-previous.ps1').write_text(manual,encoding='utf-8-sig')
    # A plain-text record remains accessible even when no application starts.
    (directory/'RECOVERY.txt').write_text(
        f'Previous application: {previous}\nPrevious runtime backup: {backup}\n'
        f'Recovery workspace: {recovery}\nTransaction outcome: {directory / "transaction.json"}\n'
        f'Independent previous-version recovery snapshot: {value["fallback_recovery"]}\n'
        f'If the updater was interrupted, close every app instance in this edition and run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{directory / "recover-previous.ps1"}"\n'
        'If startup fails, retain this folder and the previous runtime. Open the previous application and Restore Workspace using the recovery JSON. '
        'Installed-update fallback does not change Setup registration or shortcuts; rerun the previous official Setup for a complete installation rollback.\n', encoding='utf-8')
    checkpoint('Scheduling verified update and restart')
    process = subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(path)],
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True,env=restart_environment())
    # Cancellation after scheduling must still run the callback that closes
    # this app; the independent updater is already waiting for its process.
    mark_committed()
    return {'directory': directory, 'script': path, 'request': request, 'process': process}
