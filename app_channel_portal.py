"""Hierarchical channel browser with stable-ID drag and selection."""
import re
from PySide6 import QtCore,QtWidgets,QtGui


class ChannelTree(QtWidgets.QTreeWidget):
    def mimeData(self,items):
        mime=QtCore.QMimeData()
        mime.setData('application/x-analizer-channels','\n'.join(i.data(0,QtCore.Qt.ItemDataRole.UserRole) for i in items if i.data(0,QtCore.Qt.ItemDataRole.UserRole)).encode())
        return mime


class ChannelPortal(QtWidgets.QWidget):
    visibilityRequested=QtCore.Signal(list,bool)
    plotRequested=QtCore.Signal(list)
    selectionChanged=QtCore.Signal(list)
    organizeRequested=QtCore.Signal(str)

    def __init__(self,store):
        super().__init__();self.store=store;self.visible_ids=set()
        layout=QtWidgets.QVBoxLayout(self)
        row=QtWidgets.QHBoxLayout();self.search=QtWidgets.QLineEdit();self.search.setPlaceholderText('Filter name, unit, source, properties…')
        self.regex=QtWidgets.QCheckBox('Regex');row.addWidget(self.search);row.addWidget(self.regex);layout.addLayout(row)
        self.select_all=QtWidgets.QCheckBox('Select all channels');self.select_all.setTristate(True)
        self.select_all.clicked.connect(lambda checked:self.visibilityRequested.emit(list(self.store.channels),checked))
        layout.addWidget(self.select_all)
        self.tree=ChannelTree();self.tree.setHeaderLabels(['Channel','Unit','Kind']);self.tree.setColumnHidden(2,True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setDragEnabled(True);self.tree.setMinimumWidth(280);self.tree.setIndentation(16);self.tree.setColumnWidth(0,240);self.tree.setColumnWidth(1,65)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree)
        self.tree.itemChanged.connect(self._toggle)
        self.tree.itemSelectionChanged.connect(lambda:self.selectionChanged.emit(self.selected()))
        self.tree.itemDoubleClicked.connect(lambda item,col:self.plotRequested.emit(self.selected()))
        self.search.textChanged.connect(self.rebuild);self.regex.toggled.connect(self.rebuild)
        actions=QtWidgets.QHBoxLayout()
        for text,command in [('Channel actions…','organize')]:
            button=QtWidgets.QPushButton(text);actions.addWidget(button)
            button.clicked.connect(lambda checked=False,c=command:self.organizeRequested.emit(c))
        layout.addLayout(actions)
        self.rebuild()

    def selected(self):
        return [i.data(0,QtCore.Qt.ItemDataRole.UserRole) for i in self.tree.selectedItems() if i.data(0,QtCore.Qt.ItemDataRole.UserRole)]

    def rebuild(self,*args):
        selected=set(self.selected());query=self.search.text();regex=None
        try:
            if self.regex.isChecked():regex=re.compile(query,re.I)
        except re.error:
            self.search.setStyleSheet('border:1px solid #ff8096');return
        self.search.setStyleSheet('');self.tree.blockSignals(True);self.tree.clear();groups={};datasets={}
        for c in self.store.channels.values():
            metadata=' '.join([c.name,c.unit,c.kind,c.source,str(c.attributes)])
            if query and not (regex.search(metadata) if regex else query.casefold() in metadata.casefold()):continue
            if c.dataset_id not in datasets:
                ds=self.store.datasets.get(c.dataset_id)
                root=QtWidgets.QTreeWidgetItem([ds.name if ds else 'Generated channels']);self.tree.addTopLevelItem(root);datasets[c.dataset_id]=root
            key=(c.dataset_id,c.group)
            if key not in groups:
                groups[key]=QtWidgets.QTreeWidgetItem(datasets[c.dataset_id],[c.group])
            item=QtWidgets.QTreeWidgetItem(groups[key],[c.name,c.unit,c.kind]);item.setData(0,QtCore.Qt.ItemDataRole.UserRole,c.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0,QtCore.Qt.CheckState.Checked if c.id in self.visible_ids else QtCore.Qt.CheckState.Unchecked)
            item.setToolTip(0,c.name+'\n'+c.source);item.setSelected(c.id in selected)
        self.tree.expandAll();self.tree.blockSignals(False)

    def _toggle(self,item,column):
        channel_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole)
        if channel_id:
            self.visibilityRequested.emit([channel_id],item.checkState(0)==QtCore.Qt.CheckState.Checked)

    def set_visible(self,ids):
        signature=(frozenset(ids),frozenset(self.store.channels))
        if signature==getattr(self,'_visibility_signature',None):return
        self._visibility_signature=signature
        self.visible_ids=set(signature[0])
        blocker=QtCore.QSignalBlocker(self.tree)
        iterator=QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item=iterator.value();channel_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole)
            if channel_id:item.setCheckState(0,QtCore.Qt.CheckState.Checked if channel_id in self.visible_ids else QtCore.Qt.CheckState.Unchecked)
            iterator+=1
        del blocker
        total=set(self.store.channels);checked=total & self.visible_ids
        blocker=QtCore.QSignalBlocker(self.select_all)
        self.select_all.setCheckState(QtCore.Qt.CheckState.Checked if total and checked==total else QtCore.Qt.CheckState.PartiallyChecked if checked else QtCore.Qt.CheckState.Unchecked)
        self.select_all.setText('Deselect all channels' if total and checked==total else 'Select all channels')
        self.select_all.setEnabled(bool(total))
