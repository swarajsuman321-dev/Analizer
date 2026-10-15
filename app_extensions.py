"""Current frontend-independent extension host, compatible with register_patch hooks."""
import ast
import hashlib
import importlib.util
import importlib.machinery
import json
import logging
import os
from pathlib import Path
import sys
from app_support import atomic_output


class PluginManager:
    def __init__(self,directory=None):
        if directory is None:
            base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
            if not os.access(base,os.W_OK):base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'ApplianceSignalStudio'
            directory=base/'patches'
        self.directory=Path(directory);self.config=self.directory.parent/'patches_config.json'
        self.custom_kpi_hooks=[];self.custom_plot_hooks=[];self.custom_sync_hooks={}
        self.patch_errors={};self.patch_descriptions={};self._loaded_modules={};self.patch_states={}
        self.logger=logging.getLogger('appliance_signal_studio')

    @staticmethod
    def valid_name(name):
        return isinstance(name,str) and name.lower().endswith('.py') and Path(name).name==name and '/' not in name and '\\' not in name

    def files(self):
        return sorted(p.name for p in self.directory.iterdir() if p.is_file() and self.valid_name(p.name)) if self.directory.exists() else []

    def save_states(self,states):
        self.directory.mkdir(parents=True,exist_ok=True)
        with atomic_output(self.config) as temporary:Path(temporary).write_text(json.dumps(states,indent=2),encoding='utf-8')
        self.patch_states=states

    def reload(self):
        self.custom_kpi_hooks.clear();self.custom_plot_hooks.clear();self.custom_sync_hooks.clear()
        for name,module in self._loaded_modules.items():
            if sys.modules.get(name) is module:sys.modules.pop(name,None)
        self._loaded_modules.clear();self.patch_errors.clear();self.patch_descriptions.clear()
        states=json.loads(self.config.read_text(encoding='utf-8')) if self.config.exists() else {}
        if not isinstance(states,dict) or any(not self.valid_name(k) or not isinstance(v,bool) for k,v in states.items()):
            raise ValueError('Plugin settings must map Python filenames to true or false; no plugins were loaded')
        self.patch_states=states
        for name in self.files():
            if states.get(name,True):self._apply_patch(str(self.directory/name))
        return self.patch_errors

    def install(self,path):
        path=Path(path);name=path.name
        if not self.valid_name(name):raise ValueError('Choose a .py extension')
        content=path.read_bytes();compile(content,str(path),'exec')
        self.directory.mkdir(parents=True,exist_ok=True);destination=self.directory/name
        previous=destination.read_bytes() if destination.exists() else None
        try:
            with atomic_output(destination) as temporary:Path(temporary).write_bytes(content)
            self.save_states({**self.patch_states,name:True})
        except Exception:
            if previous is None:destination.unlink(missing_ok=True)
            else:
                with atomic_output(destination) as temporary:Path(temporary).write_bytes(previous)
            raise
        self.reload()
        if name in self.patch_errors:raise ValueError(self.patch_errors[name])

    def set_enabled(self,name,enabled):
        if name not in self.files():raise ValueError('Extension not found')
        self.save_states({**self.patch_states,name:bool(enabled)});self.reload()

    def remove(self,name):
        if not self.valid_name(name) or name not in self.files():raise ValueError('Extension not found')
        content=(self.directory/name).read_bytes();states=dict(self.patch_states)
        try:
            (self.directory/name).unlink();self.save_states({k:v for k,v in states.items() if k!=name})
        except Exception:
            with atomic_output(self.directory/name) as temporary:Path(temporary).write_bytes(content)
            raise
        self.reload()

    def _apply_patch(self, filepath):
        filename = os.path.basename(filepath)
        original_kpi, original_plot, original_sync = self.custom_kpi_hooks, self.custom_plot_hooks, self.custom_sync_hooks
        before_kpi, before_plot, before_sync = list(original_kpi), list(original_plot), dict(original_sync)
        digest = hashlib.sha256(os.path.abspath(filepath).encode('utf-8')).hexdigest()[:16]
        name = f'appliance_signal_patch_{digest}'
        module = None
        try:
            with open(filepath, 'rb') as source:
                content = source.read()
            code = compile(content, filepath, 'exec')
            doc = ast.get_docstring(ast.parse(content, filename=filepath))
            self.patch_descriptions[filename] = doc.splitlines()[0].strip() if doc else 'Dynamic Plugin'
            spec = importlib.util.spec_from_file_location(
                name, filepath, loader=importlib.machinery.SourceFileLoader(name, filepath)
            )
            if spec is None or spec.loader is None:
                raise ValueError('The plugin could not be loaded as a Python module.')
            mod = importlib.util.module_from_spec(spec)
            module = mod
            sys.modules[name] = mod
            # Compile fresh source rather than reusing a timestamp-based .pyc
            # after a same-sized plugin update within the same second.
            exec(code, mod.__dict__)
            register = getattr(mod, 'register_patch', None)
            if not callable(register):
                raise TypeError('The plugin must define a callable register_patch(manager).')
            register(self)
            if not isinstance(self.custom_kpi_hooks, list) or not isinstance(self.custom_plot_hooks, list) or not isinstance(self.custom_sync_hooks, dict):
                raise TypeError('KPI and plot hooks must be lists; sync hooks must be a dictionary.')
            if any(not callable(hook) for hook in self.custom_kpi_hooks + self.custom_plot_hooks):
                raise TypeError('Every KPI and plot hook must be callable.')
            if any(not isinstance(label, str) or not label.strip() or not callable(hook)
                   for label, hook in self.custom_sync_hooks.items()):
                raise TypeError('Every sync hook requires a non-empty name and a callable function.')
            if (any(self.custom_sync_hooks.get(label) is not hook for label, hook in before_sync.items())
                    or any(index >= len(self.custom_kpi_hooks) or self.custom_kpi_hooks[index] is not hook
                           for index, hook in enumerate(before_kpi))
                    or any(index >= len(self.custom_plot_hooks) or self.custom_plot_hooks[index] is not hook
                           for index, hook in enumerate(before_plot))):
                raise ValueError('A plugin cannot remove or overwrite hooks registered by another plugin.')
            if (len(self.custom_kpi_hooks) == len(before_kpi) and len(self.custom_plot_hooks) == len(before_plot)
                    and len(self.custom_sync_hooks) == len(before_sync)):
                raise ValueError('register_patch must add at least one sync, plot, or KPI hook.')
            registered_kpi, registered_plot, registered_sync = list(self.custom_kpi_hooks), list(self.custom_plot_hooks), dict(self.custom_sync_hooks)
            self.custom_kpi_hooks, self.custom_plot_hooks, self.custom_sync_hooks = original_kpi, original_plot, original_sync
            original_kpi[:] = registered_kpi
            original_plot[:] = registered_plot
            original_sync.clear()
            original_sync.update(registered_sync)
            self._loaded_modules[name] = mod
            self.logger.info("Plugin '%s' registered", filename)
            return True
        except (Exception, SystemExit) as exc:
            self.custom_kpi_hooks, self.custom_plot_hooks, self.custom_sync_hooks = original_kpi, original_plot, original_sync
            original_kpi[:] = before_kpi
            original_plot[:] = before_plot
            original_sync.clear()
            original_sync.update(before_sync)
            if module is not None and sys.modules.get(name) is module:
                sys.modules.pop(name, None)
            self.patch_errors[filename] = f'{type(exc).__name__}: {exc}'
            self.logger.error("Plugin '%s' registration failed", filename, exc_info=True)
            return False
