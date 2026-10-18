"""Install a complete verified Setup package; never overwrite a one-folder EXE."""
import os
from pathlib import Path
import subprocess
import sys


def launch_setup_update(download, recovery, directory, manifest):
    from app_installation import installed_root
    from app_updates import ps_quote, restart_environment
    root = installed_root() or Path(os.environ['LOCALAPPDATA'])/'Programs'/'ApplianceSignalStudio'
    previous = Path(sys.executable).resolve()
    target = root/'versions'/manifest['version']/'ApplianceSignalStudio.exe'
    script = Path(directory)/'install-setup-update.ps1'
    # Setup retains the complete previous runtime. Its own transaction performs
    # the health check before registering the new shortcuts/version.
    script.write_text(f'''$ErrorActionPreference = 'Stop'
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
Get-ChildItem Env: | Where-Object {{ $_.Name -like '_PYI_*' -or $_.Name -eq '_MEIPASS2' }} | ForEach-Object {{ Remove-Item -LiteralPath ('Env:' + $_.Name) }}
$download = {ps_quote(download)}
$previous = {ps_quote(previous)}
$target = {ps_quote(target)}
$recovery = {ps_quote(recovery)}
$log = {ps_quote(Path(directory)/'setup-update.log')}
Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue
try {{
    $actualHash = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne {ps_quote(manifest['sha256'])}) {{ throw 'Installer checksum changed' }}
    $arguments = @('/SILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART',
        {ps_quote('/DIR="'+str(root)+'"')}, {ps_quote('/LOG="'+str(Path(directory)/'setup-install.log')+'"')})
    $setup = Start-Process -FilePath $download -ArgumentList $arguments -Wait -PassThru
    if ($setup.ExitCode -ne 0) {{ throw ('Setup failed with exit code ' + $setup.ExitCode) }}
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {{ throw 'New runtime is missing' }}
    Start-Process -FilePath $target -ArgumentList @('--restore', ('"' + $recovery + '"'))
}} catch {{
    $_ | Out-File -LiteralPath $log
    Start-Process -FilePath $previous -ArgumentList @('--restore', ('"' + $recovery + '"'))
}}
''', encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],
                     creationflags=subprocess.CREATE_NO_WINDOW,close_fds=True,env=restart_environment())
