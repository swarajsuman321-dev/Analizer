"""Offline version manuals and non-blocking release updates."""
from pathlib import Path
import sys
from PySide6 import QtCore,QtGui,QtWidgets
from app_version import VERSION
from app_updates import check_latest,download_update,launch_installer,version_tuple,RELEASES


class UpdateTask(QtCore.QThread):
    result=QtCore.Signal(object,object)
    progress=QtCore.Signal(int)
    def __init__(self,fn,parent):super().__init__(parent);self.fn=fn
    def run(self):
        try:self.result.emit(self.fn(),None)
        except Exception as exc:self.result.emit(None,str(exc))


class InfoTab(QtWidgets.QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.manifest=None;self.download=None;self.task=None
        layout=QtWidgets.QVBoxLayout(self)
        title=QtWidgets.QLabel(f'<h2>Appliance Signal Studio {VERSION}</h2>');layout.addWidget(title)
        row=QtWidgets.QHBoxLayout();self.check_button=QtWidgets.QPushButton('Check for updates');self.install_button=QtWidgets.QPushButton('Download update');self.install_button.setEnabled(False)
        self.cancel_button=QtWidgets.QPushButton('Cancel download');self.cancel_button.hide()
        row.addWidget(self.check_button);row.addWidget(self.install_button);row.addWidget(self.cancel_button);row.addStretch();layout.addLayout(row)
        self.status=QtWidgets.QLabel('Updates are checked only when you choose. Your recordings stay on this computer.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QtWidgets.QProgressBar();self.progress.hide();layout.addWidget(self.progress)
        self.notes=QtWidgets.QLabel();self.notes.setTextFormat(QtCore.Qt.TextFormat.PlainText);self.notes.setWordWrap(True);layout.addWidget(self.notes)
        row=QtWidgets.QHBoxLayout();row.addWidget(QtWidgets.QLabel('User manual for version:'));self.versions=QtWidgets.QComboBox();row.addWidget(self.versions);row.addStretch();layout.addLayout(row)
        self.manual=QtWidgets.QTextBrowser();self.manual.setOpenExternalLinks(True);layout.addWidget(self.manual,1)
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'manuals'
        self.manuals={p.stem.removeprefix('v'):p for p in root.glob('v*.md')}
        for version in sorted(self.manuals,key=version_tuple,reverse=True):self.versions.addItem(version)
        self.versions.currentTextChanged.connect(self.show_manual);self.show_manual(self.versions.currentText())
        self.check_button.clicked.connect(self.check);self.install_button.clicked.connect(self.update);self.cancel_button.clicked.connect(self.cancel_download)

    def show_manual(self,version):
        path=self.manuals.get(version)
        self.manual.setMarkdown(path.read_text(encoding='utf-8') if path else 'The manual is unavailable in this build. See the repository documentation.')

    def run_task(self,fn,complete):
        self.check_button.setEnabled(False);self.install_button.setEnabled(False)
        self.task=UpdateTask(fn,self);self.task.result.connect(complete);self.task.progress.connect(self.progress.setValue)
        task=self.task;task.finished.connect(lambda:self.task_finished(task));task.finished.connect(task.deleteLater);task.start()

    def check(self):
        self.manifest=None;self.download=None;self.install_button.setText('Download update');self.notes.clear();self.status.setText('Checking GitHub Releases…')
        self.run_task(check_latest,self.checked)

    def checked(self,result,error):
        self.check_button.setEnabled(True);self.install_button.setEnabled(False)
        if error:self.status.setText('Could not check for updates. Check your connection and try again. '+error);return
        self.manifest=result
        if version_tuple(result['version'])<=version_tuple(VERSION):self.status.setText(f'You have the latest version ({VERSION}).');return
        self.status.setText(f"Version {result['version']} is available ({result['size']/1024/1024:.0f} MB).")
        self.notes.setText(str(result.get('notes','')))
        self.install_button.setEnabled(True)

    def update(self):
        if self.window.busy:self.status.setText('Wait for data processing to finish before updating.');return
        if self.download:
            try:
                from app_workspace_io import save_workspace
                directory=self.update_directory();recovery=directory/'recovery.json'
                self.window.mutate();save_workspace(str(recovery),self.window.store,[w.state() for w in self.window.workspaces],self.window.ui_state())
                launch_installer(self.download,recovery,directory,self.manifest['sha256'])
                self.window.close()
            except Exception as exc:self.status.setText('Could not install update. '+str(exc))
            return
        self.progress.setValue(0);self.progress.show();self.cancel_button.show();self.status.setText('Downloading and verifying the update. You can continue working.')
        self.run_task(lambda:download_update(self.manifest,self.update_directory(),self.download_progress),self.downloaded)

    def update_directory(self):
        path=Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation))/'updates'
        path.mkdir(parents=True,exist_ok=True);return path

    def downloaded(self,result,error):
        self.check_button.setEnabled(True);self.progress.hide();self.cancel_button.hide()
        if error:self.status.setText('Download failed. '+error);self.install_button.setEnabled(True);return
        self.download=result
        if sys.platform=='win32' and getattr(sys,'frozen',False):
            self.install_button.setText('Install update & restart');self.install_button.setEnabled(True)
            self.status.setText('Update verified. Install saves a recovery workspace and restarts the app. The previous executable is kept as a backup.')
        else:self.status.setText(f'Update verified and saved to {result}. Automatic installation requires the Windows app.')

    def download_progress(self,value):
        task=QtCore.QThread.currentThread()
        if task.isInterruptionRequested():raise InterruptedError('Download cancelled; the installed app is unchanged.')
        task.progress.emit(value)

    def cancel_download(self):
        if self.task:self.task.requestInterruption();self.status.setText('Cancelling download…')

    def task_finished(self,task):
        if self.task is task:self.task=None

    def prepare_close(self):
        if self.task and self.task.isRunning():
            self.task.requestInterruption();self.status.setText('Finishing the current network request before closing…')
            if not getattr(self,'_closing',False):self._closing=True;self.task.finished.connect(self.window.close)
            return False
        return True
