import os
import sys
import json
import importlib.util
import importlib.machinery
import ast
import hashlib
import logging
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from app_support import atomic_output

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _get_writable_storage_dir():
    """Use the app folder when writable, otherwise store user data in LocalAppData."""
    app_dir = get_base_dir()
    candidates = [
        app_dir,
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ApplianceSignalStudio")
    ]
    for base_dir in candidates:
        patches_dir = os.path.join(base_dir, "patches")
        try:
            os.makedirs(patches_dir, exist_ok=True)
            with tempfile.TemporaryFile(dir=patches_dir):
                pass
            return base_dir
        except OSError:
            continue
    raise OSError("The app cannot create a writable plugin folder in the app directory or LocalAppData.")

STORAGE_DIR = _get_writable_storage_dir()
PATCHES_DIR = os.path.join(STORAGE_DIR, "patches")
CONFIG_FILE = os.path.join(STORAGE_DIR, "patches_config.json")

class PatchManager:
    def __init__(self, on_change=None):
        if on_change is not None and not callable(on_change):
            raise TypeError("The plugin change callback must be callable.")
        self.on_change = on_change
        self.logger = logging.getLogger('appliance_signal_studio')
        self._config_error = None
        self._loaded_modules = {}
        self._tree_filenames = {}
        self.patch_errors = {}
        self.patch_descriptions = {}
        self.custom_kpi_hooks = []
        self.custom_plot_hooks = []
        self.custom_sync_hooks = {}
        self.patch_states = self._load_patch_config()

    @staticmethod
    def _valid_filename(filename):
        return (isinstance(filename, str) and filename.lower().endswith('.py')
                and os.path.basename(filename) == filename
                and '/' not in filename and '\\' not in filename)

    def _load_patch_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if (not isinstance(data, dict) or any(
                        not self._valid_filename(name) or not isinstance(enabled, bool)
                        for name, enabled in data.items()
                    )):
                        raise ValueError("Plugin configuration must map Python filenames to true or false.")
                    self._config_error = None
                    return data
            except Exception as exc:
                self._config_error = f"Could not read plugin configuration: {exc}"
                self.logger.error(self._config_error, exc_info=True)
                return {}
        self._config_error = None
        return {}

    def _save_patch_config(self, states=None):
        states = self.patch_states if states is None else states
        with atomic_output(CONFIG_FILE) as temporary:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(states, stream, indent=2, sort_keys=True)
                stream.write('\n')
        self._config_error = None

    def _dialog_parent(self):
        parent = getattr(self, '_ui_parent', None)
        return parent.winfo_toplevel() if parent is not None and parent.winfo_exists() else None

    def _report_error(self, title, error, show_dialog=True):
        detail = str(error)
        self.logger.error('%s: %s', title, detail)
        if hasattr(self, 'status_text'):
            self.status_text.set(detail)
        if show_dialog and self._dialog_parent() is not None:
            messagebox.showerror(title, detail, parent=self._dialog_parent())

    @staticmethod
    def _write_bytes(destination, content):
        with atomic_output(destination) as temporary:
            with open(temporary, 'wb') as stream:
                stream.write(content)

    def _patch_files(self):
        return sorted(
            (filename for filename in os.listdir(PATCHES_DIR)
             if self._valid_filename(filename) and os.path.isfile(os.path.join(PATCHES_DIR, filename))),
            key=lambda name: (name.casefold(), name)
        )

    def _states_for_update(self):
        states = dict(self.patch_states)
        if self._config_error:
            # Repairing one preference must not silently enable all other
            # plugins whose previous disabled states could not be read.
            for filename in self._patch_files():
                states.setdefault(filename, False)
        return states

    def _selected_filename(self):
        if not hasattr(self, 'patch_tree'):
            return None
        selected = self.patch_tree.selection()
        return self._tree_filenames.get(selected[0]) if selected else None

    def _update_selection_buttons(self, _event=None):
        enabled = self._selected_filename() is not None
        for button in (self.toggle_button, self.delete_button):
            button.state(['!disabled'] if enabled else ['disabled'])

    def setup_ui(self, parent_tab):
        self._ui_parent = parent_tab
        mgr_frame = ttk.LabelFrame(parent_tab, text="Plugin & Standards Evaluation Studio", padding=15)
        mgr_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        btn_row = ttk.Frame(mgr_frame)
        btn_row.pack(fill=tk.X, pady=8)

        ttk.Button(btn_row, text="📥 Install Patch (.py)", command=self.install_patch).pack(side=tk.LEFT, padx=5)
        self.toggle_button = ttk.Button(btn_row, text="🔘 Toggle Enable / Disable", command=self.toggle_selected_patch)
        self.toggle_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(btn_row, text="🗑️ Delete Patch", command=self.delete_selected_patch)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="🔄 Reload Plugins", command=lambda: self.load_installed_patches(show_errors=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="📁 Open Directory", command=self.open_patches_folder).pack(side=tk.LEFT, padx=5)

        columns = ("status", "filename", "description")
        table_frame = ttk.Frame(mgr_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.patch_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        for col, width in [("status", 120), ("filename", 260), ("description", 650)]:
            self.patch_tree.heading(col, text=col.capitalize())
            self.patch_tree.column(col, width=width, anchor=tk.W if col != "status" else tk.CENTER)
        self.patch_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vertical = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.patch_tree.yview)
        horizontal = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.patch_tree.xview)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        self.patch_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.patch_tree.tag_configure('error', foreground='#B42318')
        self.patch_tree.tag_configure('active', foreground='#17663A')
        self.patch_tree.tag_configure('inactive', foreground='#596579')
        self.patch_tree.bind("<Double-1>", lambda e: self.toggle_selected_patch())
        self.patch_tree.bind('<<TreeviewSelect>>', self._update_selection_buttons)
        self.status_text = tk.StringVar(master=parent_tab, value='')
        ttk.Label(mgr_frame, textvariable=self.status_text, wraplength=1050).pack(fill=tk.X, pady=(4, 0))
        self.load_installed_patches()

    def install_patch(self):
        p = filedialog.askopenfilename(filetypes=[("Python Patch File", "*.py")], parent=self._dialog_parent())
        if not p:
            return
        fname = os.path.basename(p)
        destination = os.path.join(PATCHES_DIR, fname)
        previous_content = None
        copied = False
        try:
            if not self._valid_filename(fname):
                raise ValueError('Choose a Python plugin file ending in .py.')
            # Read completely before opening the destination. Selecting an
            # already installed file can no longer truncate that same file.
            with open(p, 'rb') as source:
                content = source.read()
            compile(content, fname, 'exec')
            if os.path.exists(destination):
                with open(destination, 'rb') as previous:
                    previous_content = previous.read()
            self._write_bytes(destination, content)
            copied = True
            states = self._states_for_update()
            states[fname] = True
            self._save_patch_config(states)
            self.patch_states = states
        except Exception as exc:
            if copied:
                try:
                    if previous_content is None:
                        os.remove(destination)
                    else:
                        self._write_bytes(destination, previous_content)
                except OSError as rollback_error:
                    self.logger.error('Plugin install rollback failed: %s', rollback_error, exc_info=True)
                    exc = RuntimeError(f'{exc}\nThe previous plugin file could not be restored: {rollback_error}')
            self._report_error('Plugin Installation Error', exc)
            return
        try:
            reloaded = self.load_installed_patches()
        except Exception as exc:
            self._report_error('Plugin Reload Error', f"'{fname}' was installed, but its controls could not refresh: {exc}")
            return
        if not reloaded:
            self._report_error('Plugin Reload Error', f"'{fname}' was installed, but the plugin folder could not be reloaded. Check the plugin status and try Reload Plugins.")
            return
        if fname in self.patch_errors:
            self._report_error('Plugin Registration Error', f"'{fname}' was copied but could not be activated:\n{self.patch_errors[fname]}")
        else:
            messagebox.showinfo('Plugin Installed', f"Patch '{fname}' installed and registered.", parent=self._dialog_parent())

    def toggle_selected_patch(self):
        fname = self._selected_filename()
        if fname is None:
            return
        try:
            states = self._states_for_update()
            states[fname] = not states.get(fname, self._config_error is None)
            self._save_patch_config(states)
        except Exception as exc:
            self._report_error('Plugin Configuration Error', f'The enable/disable change was not saved: {exc}')
            return
        self.patch_states = states
        self.load_installed_patches()
        if states[fname] and fname in self.patch_errors:
            self._report_error('Plugin Registration Error', self.patch_errors[fname])

    def delete_selected_patch(self):
        fname = self._selected_filename()
        if fname is None:
            return
        if messagebox.askyesno("Confirm Delete", f"Delete '{fname}' permanently?", parent=self._dialog_parent()):
            previous_config = None
            previous_error = self._config_error
            saved = False
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'rb') as configuration:
                        previous_config = configuration.read()
                states = self._states_for_update()
                states.pop(fname, None)
                self._save_patch_config(states)
                saved = True
                p = os.path.join(PATCHES_DIR, fname)
                if os.path.exists(p):
                    os.remove(p)
                self.patch_states = states
            except Exception as exc:
                if saved:
                    try:
                        if previous_config is None:
                            os.remove(CONFIG_FILE)
                        else:
                            self._write_bytes(CONFIG_FILE, previous_config)
                        self._config_error = previous_error
                    except OSError as rollback_error:
                        self.logger.error('Plugin deletion rollback failed: %s', rollback_error, exc_info=True)
                        exc = RuntimeError(f'{exc}\nThe previous plugin settings could not be restored: {rollback_error}')
                self._report_error('Plugin Removal Error', exc)
                return
            self.load_installed_patches(show_errors=True)

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

    def load_installed_patches(self, show_errors=False):
        states = self._load_patch_config()
        try:
            files = self._patch_files()
        except OSError as exc:
            self._report_error('Plugin Reload Error', f'Could not read the plugin directory: {exc}', show_errors)
            return False
        self.patch_states = states
        self.custom_kpi_hooks.clear()
        self.custom_plot_hooks.clear()
        self.custom_sync_hooks.clear()
        for name, module in self._loaded_modules.items():
            if sys.modules.get(name) is module:
                sys.modules.pop(name, None)
        self._loaded_modules.clear()
        self.patch_errors.clear()
        self.patch_descriptions.clear()
        for fname in files:
            if self._config_error:
                self.patch_errors[fname] = self._config_error
            elif self.patch_states.get(fname, True):
                self._apply_patch(os.path.join(PATCHES_DIR, fname))
        self._update_treeview(files)
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception as exc:
                self._report_error('Plugin Refresh Error', f'Plugins loaded, but the application controls could not refresh: {exc}', show_errors)
        errors = self._config_error or '; '.join(f'{name}: {error}' for name, error in self.patch_errors.items())
        if errors and show_errors:
            self._report_error('Plugin Load Errors', errors)
        return self._config_error is None

    def _update_treeview(self, files=None):
        if not hasattr(self, 'patch_tree'):
            return
        selected = self._selected_filename()
        for item in self.patch_tree.get_children():
            self.patch_tree.delete(item)
        self._tree_filenames.clear()
        files = self._patch_files() if files is None else files
        if not files:
            self.patch_tree.insert("", tk.END, values=("—", "No patches installed", "Use 'Install Patch' to register new hooks"))
        active = 0
        for fname in files:
            if fname in self.patch_errors:
                status, tag, doc = 'ERROR', 'error', self.patch_errors[fname]
            else:
                enabled = self.patch_states.get(fname, True)
                status, tag = ('ACTIVE', 'active') if enabled else ('INACTIVE', 'inactive')
                active += int(enabled)
                doc = self.patch_descriptions.get(fname, 'Dynamic Plugin')
                try:
                    if fname not in self.patch_descriptions:
                        with open(os.path.join(PATCHES_DIR, fname), 'rb') as source:
                            description = ast.get_docstring(ast.parse(source.read(), filename=fname))
                        if description:
                            doc = description.splitlines()[0].strip()
                except Exception:
                    pass
            item = self.patch_tree.insert("", tk.END, values=(status, fname, doc), tags=(tag,))
            self._tree_filenames[item] = fname
            if fname == selected:
                self.patch_tree.selection_set(item)
        self._update_selection_buttons()
        if self._config_error:
            self.status_text.set(f'{self._config_error} Enable individual plugins after correcting their settings.')
        else:
            self.status_text.set(f'{active} active plugin(s), {len(self.patch_errors)} error(s). Sync strategies: {len(self.custom_sync_hooks)}; plot hooks: {len(self.custom_plot_hooks)}; KPI hooks: {len(self.custom_kpi_hooks)}.')

    def open_patches_folder(self):
        try:
            os.startfile(PATCHES_DIR)
        except Exception:
            messagebox.showinfo("Directory", f"Patches path:\n{PATCHES_DIR}")
