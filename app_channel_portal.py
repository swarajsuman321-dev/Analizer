"""Hierarchical channel browser with stable-ID drag and selection."""
import re
from PySide6 import QtCore,QtWidgets,QtGui
from app_channel_identity import channel_details,dataset_aliases


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
    traceColorRequested=QtCore.Signal(list)
    comparisonRequested=QtCore.Signal(list)

    def __init__(self,store):
        super().__init__();self.store=store;self.visible_ids=set()
        layout=QtWidgets.QVBoxLayout(self)
        row=QtWidgets.QHBoxLayout();self.search=QtWidgets.QLineEdit();self.search.setPlaceholderText('Filter name, unit, source, properties…')
        self.regex=QtWidgets.QCheckBox('Regular expression');row.addWidget(self.search);row.addWidget(self.regex);layout.addLayout(row)
        self.search_error=QtWidgets.QLabel();self.search_error.setWordWrap(True)
        self.search_error.setAccessibleName('Search error');self.search_error.hide();layout.addWidget(self.search_error)
        self.search.setAccessibleName('Filter channels')
        self.tree=ChannelTree();self.tree.setHeaderLabels(['Channel','Unit'])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setDragEnabled(True);self.tree.setMinimumWidth(300);self.tree.setIndentation(16);self.tree.setColumnWidth(0,240);self.tree.setColumnWidth(1,65)
        self.tree.header().setStretchLastSection(False)
        # Give channel names all remaining width. File commands belong to each
        # source's context menu and do not reserve a column beside every trace.
        self.tree.header().setMinimumSectionSize(64)
        self.tree.header().setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
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
        selected=set(self.selected());query=self.search.text();regex=None;error=None
        try:
            if self.regex.isChecked():regex=re.compile(query,re.I)
        except re.error as exc:
            error=f'Invalid expression: {exc}. Fix the expression, clear the filter, or turn off Regular expression. No matching results are shown.'
        self.search.setStyleSheet('border:1px solid #ff8096' if error else '')
        self.search.setAccessibleDescription(error or 'Filters channels by name, unit, source and properties')
        self.search_error.setText(error or '');self.search_error.setVisible(bool(error));self.filter_valid=not error
        self.tree.blockSignals(True);self.tree.clear();groups={};datasets={};self.dataset_roots=datasets
        self.filtered_ids={id:[] for id in self.store.datasets}
        for c in self.store.channels.values():self.filtered_ids.setdefault(c.dataset_id,[])
        matches=[]
        for c in self.store.channels.values():
            metadata=' '.join([c.name,c.unit,c.kind,c.source,str(c.attributes)])
            if error or (query and not (regex.search(metadata) if regex else query.casefold() in metadata.casefold())):continue
            self.filtered_ids[c.dataset_id].append(c.id);matches.append(c)
        # Keep source roots and Close Dataset reachable even when no channel matches.
        for dataset_id in self.filtered_ids:
            datasets[dataset_id]=self.add_dataset_root(dataset_id)
        for c in matches:
            key=(c.dataset_id,c.group)
            if key not in groups:
                groups[key]=QtWidgets.QTreeWidgetItem(datasets[c.dataset_id],[c.group])
            item=QtWidgets.QTreeWidgetItem(groups[key],[c.name,c.unit]);item.setData(0,QtCore.Qt.ItemDataRole.UserRole,c.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0,QtCore.Qt.CheckState.Checked if c.id in self.visible_ids else QtCore.Qt.CheckState.Unchecked)
            details=channel_details(self.store,c)+'\nKind: '+c.kind
            item.setToolTip(0,details);item.setData(0,QtCore.Qt.ItemDataRole.AccessibleDescriptionRole,details)
            item.setSelected(c.id in selected)
        self.tree.expandAll();self.update_dataset_checks();self.tree.blockSignals(False)

    def dataset_channels(self,dataset_id):
        return [c.id for c in self.store.channels.values() if c.dataset_id==dataset_id]

    def add_dataset_root(self,dataset_id):
        root=QtWidgets.QTreeWidgetItem([dataset_aliases(self.store).get(dataset_id,'Generated channels')])
        root.setData(0,QtCore.Qt.ItemDataRole.UserRole+1,dataset_id)
        root.setFlags(root.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        self.tree.addTopLevelItem(root)
        return root

    def update_dataset_checks(self):
        for dataset_id,root in getattr(self,'dataset_roots',{}).items():
            ids=set(self.dataset_channels(dataset_id));checked=ids & self.visible_ids
            root.setCheckState(0,QtCore.Qt.CheckState.Checked if ids and checked==ids else QtCore.Qt.CheckState.PartiallyChecked if checked else QtCore.Qt.CheckState.Unchecked)
            label='Deselect All' if ids and checked==ids else 'Select All'
            ds=self.store.datasets.get(dataset_id);filtered=set(self.filtered_ids.get(dataset_id,[]));matching=len(filtered)
            count=f'{matching}/{len(ids)} results' if self.search.text() else f'{len(ids)} channels'
            root.setText(0,dataset_aliases(self.store).get(dataset_id,'Generated channels')+' — '+label+f' · {count} · {len(checked)} plotted')
            scope='file' if ds else 'group'
            commands='Close Dataset and filtered selection' if ds else 'Filtered selection'
            root.setToolTip(0,((ds.name+'\n'+ds.source+'\n') if ds else '')+label+' channels in this '+scope+' only. '+count+'. Source checkbox includes channels hidden by the filter. Right-click for '+commands.lower()+'.')

    def context_menu(self,position):
        item=self.tree.itemAt(position)
        if item is None:return
        clicked_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole)
        selected=self.selected()
        channel_ids=(selected if clicked_id in selected else [clicked_id]) if clicked_id else []
        while item.parent():item=item.parent()
        dataset_id=item.data(0,QtCore.Qt.ItemDataRole.UserRole+1)
        if dataset_id not in self.dataset_roots:return
        menu=QtWidgets.QMenu(self);ids=self.dataset_channels(dataset_id)
        if channel_ids:
            menu.addAction('Change Trace Color…',lambda:self.traceColorRequested.emit(channel_ids))
            menu.addAction('Add Selected Channels to Comparison',lambda:self.comparisonRequested.emit(channel_ids))
        else:
            compare=menu.addAction('Add This File to Comparison',lambda:self.comparisonRequested.emit(ids))
            compare.setEnabled(bool(ids))
        menu.addSeparator()
        source='File' if dataset_id in self.store.datasets else 'Group'
        menu.addAction('Select All in This '+source,lambda:self.visibilityRequested.emit(ids,True))
        menu.addAction('Deselect All in This '+source,lambda:self.visibilityRequested.emit(ids,False))
        if self.search.text():
            filtered=self.filtered_ids.get(dataset_id,[])
            for label,show in [('Select Filtered Results in This '+source,True),('Deselect Filtered Results in This '+source,False)]:
                action=menu.addAction(label,lambda checked=False,show=show:self.visibilityRequested.emit(list(filtered),show))
                action.setEnabled(self.filter_valid and bool(filtered))
        if dataset_id in self.store.datasets:
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
