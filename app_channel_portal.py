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
    removeRequested=QtCore.Signal()
    clearRequested=QtCore.Signal()
    datasetRemovalRequested=QtCore.Signal(str)

    def __init__(self,store):
        super().__init__();self.store=store;self.visible_ids=set()
        layout=QtWidgets.QVBoxLayout(self)
        row=QtWidgets.QHBoxLayout();self.search=QtWidgets.QLineEdit();self.search.setPlaceholderText('Filter name, unit, source, properties…')
        self.regex=QtWidgets.QCheckBox('Regular expression');row.addWidget(self.search);row.addWidget(self.regex);layout.addLayout(row)
        self.tree=ChannelTree();self.tree.setHeaderLabels(['Channel','Unit','Kind','File actions']);self.tree.setColumnHidden(2,True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setDragEnabled(True);self.tree.setMinimumWidth(380);self.tree.setIndentation(16);self.tree.setColumnWidth(0,240);self.tree.setColumnWidth(1,65)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(3,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu);self.tree.customContextMenuRequested.connect(self.context_menu)
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
        row=QtWidgets.QHBoxLayout();self.remove_button=QtWidgets.QPushButton('Remove recording…');self.clear_button=QtWidgets.QPushButton('Clear workspace')
        self.remove_button.setToolTip('Unload an entire recording and its derived traces. Original files are kept.')
        self.clear_button.setToolTip('Unload all recordings from both plot workspaces. Original files are kept.')
        row.addWidget(self.remove_button);row.addWidget(self.clear_button);layout.addLayout(row)
        self.remove_button.clicked.connect(self.removeRequested);self.clear_button.clicked.connect(self.clearRequested)
        self.rebuild()

    def selected(self):
        return [i.data(0,QtCore.Qt.ItemDataRole.UserRole) for i in self.tree.selectedItems() if i.data(0,QtCore.Qt.ItemDataRole.UserRole)]

    def rebuild(self,*args):
        self.remove_button.setEnabled(bool(self.store.datasets));self.clear_button.setEnabled(bool(self.store.datasets or self.store.channels))
        selected=set(self.selected());query=self.search.text();regex=None
        try:
            if self.regex.isChecked():regex=re.compile(query,re.I)
        except re.error:
            self.search.setStyleSheet('border:1px solid #ff8096');return
        self.search.setStyleSheet('');self.tree.blockSignals(True);self.tree.clear();groups={};datasets={};self.dataset_roots=datasets
        for c in self.store.channels.values():
            metadata=' '.join([c.name,c.unit,c.kind,c.source,str(c.attributes)])
            if query and not (regex.search(metadata) if regex else query.casefold() in metadata.casefold()):continue
            if c.dataset_id not in datasets:
                root=self.add_dataset_root(c.dataset_id);datasets[c.dataset_id]=root
            key=(c.dataset_id,c.group)
            if key not in groups:
                groups[key]=QtWidgets.QTreeWidgetItem(datasets[c.dataset_id],[c.group])
            item=QtWidgets.QTreeWidgetItem(groups[key],[c.name,c.unit,c.kind]);item.setData(0,QtCore.Qt.ItemDataRole.UserRole,c.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0,QtCore.Qt.CheckState.Checked if c.id in self.visible_ids else QtCore.Qt.CheckState.Unchecked)
            item.setToolTip(0,c.name+'\n'+c.source);item.setSelected(c.id in selected)
        # Source-only datasets remain removable even when they have no traces.
        if not query:
            for dataset_id in self.store.datasets:
                if dataset_id not in datasets:datasets[dataset_id]=self.add_dataset_root(dataset_id)
        self.tree.expandAll();self.update_dataset_checks();self.tree.blockSignals(False)

    def dataset_channels(self,dataset_id):
        return [c.id for c in self.store.channels.values() if c.dataset_id==dataset_id]

    def add_dataset_root(self,dataset_id):
        ds=self.store.datasets.get(dataset_id)
        root=QtWidgets.QTreeWidgetItem([ds.name if ds else 'Generated channels'])
        root.setData(0,QtCore.Qt.ItemDataRole.UserRole+1,dataset_id)
        root.setFlags(root.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        root.setToolTip(0,'Select or deselect channels in this file only'+('\n'+ds.source if ds else ''))
        self.tree.addTopLevelItem(root)
        if ds:
            button=QtWidgets.QPushButton('Close Dataset');button.setToolTip('Unload '+ds.name+'; keep the original file')
            button.clicked.connect(lambda checked=False,id=dataset_id:self.datasetRemovalRequested.emit(id))
            self.tree.setItemWidget(root,3,button)
        return root

    def update_dataset_checks(self):
        for dataset_id,root in getattr(self,'dataset_roots',{}).items():
            ids=set(self.dataset_channels(dataset_id));checked=ids & self.visible_ids
            root.setCheckState(0,QtCore.Qt.CheckState.Checked if ids and checked==ids else QtCore.Qt.CheckState.PartiallyChecked if checked else QtCore.Qt.CheckState.Unchecked)
            label='Deselect All' if ids and checked==ids else 'Select All'
            ds=self.store.datasets.get(dataset_id);root.setText(0,(ds.name if ds else 'Generated channels')+' — '+label)
            root.setToolTip(0,(ds.source+'\n' if ds else '')+label+' channels in this file only')

    def context_menu(self,position):
        item=self.tree.itemAt(position)
        if item is None:return
        while item.parent():item=item.parent()
        dataset_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole+1)
        if dataset_id not in self.store.datasets:return
        menu=QtWidgets.QMenu(self);ids=self.dataset_channels(dataset_id)
        menu.addAction('Select All in This File',lambda:self.visibilityRequested.emit(ids,True))
        menu.addAction('Deselect All in This File',lambda:self.visibilityRequested.emit(ids,False))
        menu.addSeparator();menu.addAction('Close Dataset',lambda:self.datasetRemovalRequested.emit(dataset_id))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _toggle(self,item,column):
        if column!=0:return
        dataset_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole+1)
        if dataset_id is not None:
            self.visibilityRequested.emit(self.dataset_channels(dataset_id),item.checkState(0)==QtCore.Qt.CheckState.Checked)
            return
        channel_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole)
        if channel_id:self.visibilityRequested.emit([channel_id],item.checkState(0)==QtCore.Qt.CheckState.Checked)

    def set_visible(self,ids):
        self.visible_ids=set(ids)
        blocker=QtCore.QSignalBlocker(self.tree)
        iterator=QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item=iterator.value();channel_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole)
            if channel_id:item.setCheckState(0,QtCore.Qt.CheckState.Checked if channel_id in self.visible_ids else QtCore.Qt.CheckState.Unchecked)
            iterator+=1
        self.update_dataset_checks()
        del blocker
