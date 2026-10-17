"""Offline version manuals and non-blocking release updates."""
import re
from pathlib import Path
import sys
from PySide6 import QtCore,QtGui,QtWidgets
from app_version import VERSION
from app_updates import check_latest,download_update,launch_installer,version_tuple,RELEASES,import_offline_update,network_hint


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
        from app_output import output_directory
        output_row=QtWidgets.QHBoxLayout();output_label=QtWidgets.QLabel('Output folder: '+str(output_directory()));output_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse);output_label.setWordWrap(True)
        open_output=QtWidgets.QPushButton('Open output folder');open_output.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(output_directory()))))
        output_row.addWidget(output_label,1);output_row.addWidget(open_output);layout.addLayout(output_row)
        from app_lifecycle import settings_directory
        settings_row=QtWidgets.QHBoxLayout();settings_label=QtWidgets.QLabel('Settings and templates: '+str(settings_directory()));settings_label.setWordWrap(True);settings_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        settings_button=QtWidgets.QPushButton('Open Settings Folder');settings_button.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(settings_directory()))))
        settings_row.addWidget(settings_label,1);settings_row.addWidget(settings_button);layout.addLayout(settings_row)
        row=QtWidgets.QHBoxLayout();self.check_button=QtWidgets.QPushButton('Check for updates');self.install_button=QtWidgets.QPushButton('Download update');self.install_button.setEnabled(False)
        self.cancel_button=QtWidgets.QPushButton('Cancel download');self.cancel_button.hide();self.offline_button=QtWidgets.QPushButton('Import offline update…')
        row.addWidget(self.check_button);row.addWidget(self.install_button);row.addWidget(self.offline_button);row.addWidget(self.cancel_button);row.addStretch();layout.addLayout(row)
        self.status=QtWidgets.QLabel('Updates are checked only when you choose. Your recordings stay on this computer.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QtWidgets.QProgressBar();self.progress.hide();layout.addWidget(self.progress)
        self.notes=QtWidgets.QLabel();self.notes.setTextFormat(QtCore.Qt.TextFormat.PlainText);self.notes.setWordWrap(True);layout.addWidget(self.notes)
        from app_version import BUILD_DATE
        details=QtWidgets.QTabWidget();layout.addWidget(details,1)
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'manuals'
        current=root/f'v{VERSION}.md'
        release=QtWidgets.QTextBrowser();release.setMarkdown(current.read_text(encoding='utf-8').split('## Quick start')[0] if current.exists() else 'See the official GitHub release notes.');details.addTab(release,'Release Notes')
        history=QtWidgets.QTextBrowser();history.setMarkdown('\n\n'.join(p.read_text(encoding='utf-8').split('## Quick start')[0] for p in sorted(root.glob('v*.md'),key=lambda p:version_tuple(p.stem[1:]),reverse=True)));details.addTab(history,'Changelog')
        license=QtWidgets.QTextBrowser();license.setPlainText('Application license: no distribution license has been declared in this repository. Rights remain with the respective rights holders.\n\nThird-party components retain their own licenses: Qt/PySide6 (LGPLv3/GPLv3/commercial), NumPy and pandas (BSD), SciPy (BSD), Matplotlib (PSF-based), pyqtgraph (MIT), npTDMS (LGPLv3). See the component distributions for their full license notices.');details.addTab(license,'License')
        layout.insertWidget(1,QtWidgets.QLabel('Build date: '+BUILD_DATE))
        self.help=ManualHelp(window)
        # Keep the manual API available to existing bundle checks; its widget
        # lives exclusively in the separate nonmodal Help window.
        for name in ('manuals','manual','topics','search','next_match','search_status','versions'):setattr(self,name,getattr(self.help,name))
        self.check_button.clicked.connect(self.check);self.install_button.clicked.connect(self.update);self.cancel_button.clicked.connect(self.cancel_download);self.offline_button.clicked.connect(self.import_offline)

    def run_task(self,fn,complete):
        self.check_button.setEnabled(False);self.install_button.setEnabled(False);self.offline_button.setEnabled(False)
        self.task=UpdateTask(fn,self);self.task.result.connect(complete);self.task.progress.connect(self.progress.setValue)
        task=self.task;task.finished.connect(lambda:self.task_finished(task));task.finished.connect(task.deleteLater);task.start()

    def check(self):
        self.manifest=None;self.download=None;self.install_button.setText('Download update');self.notes.clear();self.status.setText('Checking GitHub Releases…')
        self.run_task(check_latest,self.checked)

    def checked(self,result,error):
        self.check_button.setEnabled(True);self.install_button.setEnabled(False);self.offline_button.setEnabled(True)
        if error:self.status.setText('Could not check for updates. '+network_hint(error));self.offline_button.setEnabled(True);return
        self.manifest=result
        if version_tuple(result['version'])<=version_tuple(VERSION):self.status.setText(f'You have the latest version ({VERSION}).');return
        self.status.setText(f"Version {result['version']} is available ({result['size']/1024/1024:.0f} MB).")
        self.notes.setText(str(result.get('notes','')))
        self.install_button.setEnabled(True)

    def import_offline(self):
        if self.task and self.task.isRunning():
            self.status.setText('Finish the current update operation first.')
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Select approved update manifest', '',
            'Update manifest (update.json);;JSON files (*.json)')
        if not filename:
            return
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText('Validating approved offline update…')
        self.run_task(lambda: import_offline_update(
            filename, self.update_directory(), self.download_progress), self.offline_imported)

    def offline_imported(self, result, error):
        self.check_button.setEnabled(True)
        self.offline_button.setEnabled(True)
        self.progress.hide()
        if error:
            self.status.setText('Offline update rejected: ' + str(error))
            return
        manifest, download = result
        if version_tuple(manifest['version']) <= version_tuple(VERSION):
            self.status.setText('This package is not newer than the installed version.')
            return
        self.manifest, self.download = manifest, download
        self.notes.setText(str(manifest.get('notes', '')))
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            self.install_button.setText('Install update & restart')
            self.install_button.setEnabled(True)
            self.status.setText(f"Offline update v{manifest['version']} verified. Ready to install.")
        else:
            self.status.setText(f'Offline package verified at {download}. Installation requires the Windows EXE.')

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
        self.check_button.setEnabled(True);self.offline_button.setEnabled(True);self.progress.hide();self.cancel_button.hide()
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


class ManualHelp(QtWidgets.QWidget):
    """Searchable offline documentation independent of the modal About window."""
    def __init__(self,parent=None):
        super().__init__(parent);layout=QtWidgets.QVBoxLayout(self)
        row=QtWidgets.QHBoxLayout();row.addWidget(QtWidgets.QLabel('User manual for version:'));self.versions=QtWidgets.QComboBox();row.addWidget(self.versions);row.addStretch();layout.addLayout(row)
        row=QtWidgets.QHBoxLayout();self.topics=QtWidgets.QComboBox();self.topics.setMinimumContentsLength(22);self.topics.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search=QtWidgets.QLineEdit();self.search.setPlaceholderText('Find a feature or keyword…');self.next_match=QtWidgets.QPushButton('Find next')
        row.addWidget(self.topics,1);row.addWidget(self.search,1);row.addWidget(self.next_match);layout.addLayout(row)
        self.search_status=QtWidgets.QLabel();layout.addWidget(self.search_status)
        self.topics.currentIndexChanged.connect(self.jump_topic);self.search.returnPressed.connect(self.find_manual);self.next_match.clicked.connect(self.find_manual)
        self.manual=QtWidgets.QTextBrowser();self.manual.setOpenExternalLinks(True);layout.addWidget(self.manual,1)
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'manuals'
        self.manuals={p.stem.removeprefix('v'):p for p in root.glob('v*.md')}
        for version in sorted(self.manuals,key=version_tuple,reverse=True):self.versions.addItem(version)
        self.versions.currentTextChanged.connect(self.show_manual);self.show_manual(self.versions.currentText())

    def show_manual(self,version):
        path=self.manuals.get(version)
        content=path.read_text(encoding='utf-8') if path else 'The manual is unavailable in this build. See the repository documentation.'
        self.manual.setMarkdown(content);self.search_status.clear();self.search.clear();self.topics.blockSignals(True);self.topics.clear()
        self.topics.addItems(re.findall(r'^## (.+)$',content,re.M));self.topics.blockSignals(False)
        self.manual.moveCursor(QtGui.QTextCursor.MoveOperation.Start)

    def jump_topic(self,index):
        heading=self.topics.itemText(index);block=self.manual.document().firstBlock()
        while block.isValid():
            if block.blockFormat().headingLevel()==2 and block.text()==heading:
                cursor=self.manual.textCursor();cursor.setPosition(block.position());self.manual.setTextCursor(cursor);self.manual.ensureCursorVisible();return
            block=block.next()

    def find_manual(self):
        query=self.search.text().strip()
        if not query:self.search_status.clear();return
        original=self.manual.textCursor();found=self.manual.find(query)
        if not found:
            self.manual.moveCursor(QtGui.QTextCursor.MoveOperation.Start);found=self.manual.find(query)
        if not found:self.manual.setTextCursor(original)
        self.search_status.setText('' if found else 'No matches in this version’s manual.')
