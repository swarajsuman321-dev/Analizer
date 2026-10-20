"""Migrate personal configuration without deleting another edition or recovery.

Discovery never grants ownership of another installation. Setup manages its
installed payloads; each updater manages only its own transaction backup.
The explicit legacy inventory helper remains available for compatibility.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from app_version import VERSION
from app_support import atomic_output

PRODUCT='Appliance Signal Studio'


def settings_directory():
    override=os.environ.get('ANALIZER_SETTINGS_DIR') or os.environ.get('ANALIZER_OUTPUT_DIR')
    root=Path(override).expanduser() if override else Path(os.environ.get('APPDATA',Path.home()/'.config'))/'ApplianceSignalStudio'
    root.mkdir(parents=True,exist_ok=True)
    return root


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_json(path,value):
    with atomic_output(path) as temporary:Path(temporary).write_text(json.dumps(value,indent=2),encoding='utf-8')


def migrate_user_files(roots,destination=None):
    """Copy settings without overwriting newer choices; preserve conflicts."""
    destination=Path(destination) if destination else settings_directory();destination.mkdir(parents=True,exist_ok=True)
    result=[]
    for base in dict.fromkeys(Path(p).resolve() for p in roots):
        if not base.is_dir() or base==destination.resolve():continue
        token=hashlib.sha256(str(base).encode()).hexdigest()[:12]
        sources=[]
        for relative in ('templates','presets','patches','settings','workspaces'):
            directory=base/relative
            if directory.is_dir():sources.extend(p for p in directory.rglob('*') if p.is_file() and not p.is_symlink())
        # A portable app may live in Downloads alongside unrelated documents.
        # Only named app configurations are eligible outside its owned folders.
        sources.extend(p for p in base.glob('*') if p.is_file() and p.suffix.lower() in ('.json','.xml','.ini','.cfg','.npz') and any(token in p.name.lower() for token in ('preset','template','workspace','settings','config','layout','channel')))
        for source in sources:
            # Do not follow links outside the discovered settings directory.
            if not source.resolve().is_relative_to(base):continue
            relative=source.relative_to(base)
            if relative.name in ('installations.json','lifecycle.json','install-inventory.json','migration.json'):continue
            target=destination/relative
            if target.exists() and digest(target)!=digest(source):target=destination/'legacy-imports'/token/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                with atomic_output(target) as temporary:shutil.copy2(source,temporary)
            if digest(target)!=digest(source):raise OSError('Settings migration verification failed: '+str(source))
            result.append({'source':str(source),'destination':str(target),'sha256':digest(target)})
    write_json(destination/'migration.json',{'version':1,'files':result})
    return result


def registry_installations():
    """Discover only exact product keys; never execute UninstallString."""
    if sys.platform!='win32':return []
    import winreg
    result=[]
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for location in (r'Software\Microsoft\Windows\CurrentVersion\Uninstall',r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
            try:
                with winreg.OpenKey(hive,location) as parent:
                    for i in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,i)) as key:
                                if winreg.QueryValueEx(key,'DisplayName')[0] in (PRODUCT,'ApplianceSignalStudio'):
                                    result.append(Path(winreg.QueryValueEx(key,'InstallLocation')[0]))
                        except OSError:continue
            except OSError:continue
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\ApplianceSignalStudio') as key:result.append(Path(winreg.QueryValueEx(key,'InstallLocation')[0]))
    except OSError:pass
    return result


def windows_product_version(path):
    """Read PE resources without launching the executable."""
    if sys.platform!='win32':return None
    import ctypes
    from ctypes import wintypes
    dll=ctypes.windll.version
    dll.GetFileVersionInfoSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)];dll.GetFileVersionInfoSizeW.restype=wintypes.DWORD
    dll.GetFileVersionInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    dll.VerQueryValueW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT)]
    unused=wintypes.DWORD();size=dll.GetFileVersionInfoSizeW(str(path),ctypes.byref(unused))
    if not size:return None
    buffer=ctypes.create_string_buffer(size)
    if not dll.GetFileVersionInfoW(str(path),0,size,buffer):return None
    def query(key):
        ptr=ctypes.c_void_p();length=wintypes.UINT()
        if not dll.VerQueryValueW(buffer,key,ctypes.byref(ptr),ctypes.byref(length)):return ctypes.c_void_p(),0
        return ptr,length.value
    ptr,length=query('\\VarFileInfo\\Translation')
    if not ptr.value or length<4:return None
    words=ctypes.cast(ptr,ctypes.POINTER(wintypes.WORD));translation=f'{words[0]:04x}{words[1]:04x}'
    values={}
    for field in ('ProductName','FileVersion'):
        ptr,length=query('\\StringFileInfo\\'+translation+'\\'+field)
        if not ptr.value:return None
        values[field]=ctypes.wstring_at(ptr.value)
    return values


def cleanup_inventory(root,inventory,current_executable):
    """Delete only unchanged inventoried binaries, never user data or the running app."""
    root=Path(root).resolve();current=Path(current_executable).resolve();removed=[];retained=[]
    if not isinstance(inventory,dict) or inventory.get('product')!=PRODUCT:return removed,['Unrecognized product inventory']
    if not isinstance(inventory.get('files',{}),dict):return removed,['Invalid file inventory']
    from app_updates import version_tuple
    if version_tuple(inventory.get('version'))>=version_tuple(VERSION):return removed,[]
    for relative,expected in inventory.get('files',{}).items():
        path=root/relative
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve()==current:retained.append(str(path));continue
        # Inventory is restricted to application executable/dependency payloads.
        named_app=path.name.lower() in ('appliancesignalstudio.exe','appliancesignalstudio.previous.exe')
        if not named_app and path.suffix.lower()=='.exe':
            metadata=windows_product_version(path);named_app=bool(metadata and metadata.get('ProductName')==PRODUCT)
        if not named_app and not (Path(relative).parts and Path(relative).parts[0]=='_internal'):
            retained.append(str(path));continue
        if not path.is_file():continue
        try:
            if digest(path)!=expected:retained.append(str(path));continue
            path.unlink();removed.append(str(path))
        except OSError:retained.append(str(path))
    # Only empty dependency directories are removed; no rmtree of install roots.
    internal=root/'_internal'
    if internal.is_dir() and not internal.is_symlink() and not getattr(internal,'is_junction',lambda:False)():
        for folder in sorted(internal.rglob('*'),reverse=True):
            if folder.is_dir() and not folder.is_symlink() and folder.resolve().is_relative_to(root) and not getattr(folder,'is_junction',lambda:False)():
                try:folder.rmdir()
                except OSError:pass
        try:internal.rmdir()
        except OSError:pass
    return removed,retained


def installation_roots():
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    roots=[base,*registry_installations()]
    record=settings_directory()/'installations.json'
    if record.exists():
        try:roots.extend(Path(p) for p in json.loads(record.read_text()).get('installations',{}))
        except (OSError,ValueError,TypeError):pass
    return list(dict.fromkeys(p.resolve() for p in roots if p.is_absolute()))


def prepare_user_data():
    roots=installation_roots()
    # Legacy portable outputs and per-user plugin locations used by earlier builds.
    sources=[p/'SignalStudio_Output' for p in roots]+roots
    local=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'ApplianceSignalStudio'
    sources.append(local)
    return migrate_user_files(sources)


def finalize_installation():
    """Called only after a normal packaged Windows startup/restore succeeds."""
    if sys.platform!='win32' or not getattr(sys,'frozen',False):return
    executable=Path(sys.executable).resolve();roots=installation_roots();home=settings_directory()
    from app_installation import installed_root
    if installed_root():
        # Inno Setup owns complete version directories and its uninstall log.
        # Never let portable cleanup remove a runtime retained for recovery.
        migrate_user_files([p/'SignalStudio_Output' for p in roots]+roots)
        write_json(home/'lifecycle.json',{'version':VERSION,'mode':'installer-managed','removed':[]})
        return
    # Migrate discovered personal configurations without deleting payloads.
    migrate_user_files([p/'SignalStudio_Output' for p in roots]+roots)
    record_path=home/'installations.json'
    try:record=json.loads(record_path.read_text()) if record_path.exists() else {'installations':{}}
    except (OSError,ValueError):record={'installations':{}}
    # A successful startup does not establish ownership of another edition,
    # nor does it authorize removing its recovery runtime. Discovery is used
    # solely for non-destructive configuration migration. Updates own their
    # specific backup; Inno owns installed payloads. Keep all recovery copies.
    removed=[];retained=[str(root) for root in roots if root!=executable.parent]
    files={executable.name:digest(executable)}
    internal=executable.parent/'_internal'
    # A one-file app must not claim ownership of leftover portable dependencies.
    if Path(getattr(sys,'_MEIPASS','')).resolve()==internal.resolve():
        for path in internal.rglob('*'):
            if path.is_file() and not path.is_symlink():files[str(path.relative_to(executable.parent))]=digest(path)
    record.setdefault('installations',{})[str(executable.parent)]={'product':PRODUCT,'version':VERSION,'files':files,'kind':'portable-zip' if Path(getattr(sys,'_MEIPASS','')).resolve()==internal.resolve() else 'portable','executable':str(executable)}
    write_json(record_path,record);write_json(home/'lifecycle.json',{'version':VERSION,'removed':removed,'retained':retained})
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\ApplianceSignalStudio') as key:
        winreg.SetValueEx(key,'InstallLocation',0,winreg.REG_SZ,str(executable.parent));winreg.SetValueEx(key,'Version',0,winreg.REG_SZ,VERSION)
