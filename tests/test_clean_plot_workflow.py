"""Plot-first user workflows across freely arranged graphs and shared values."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore, QtWidgets

from app_channel_store import Channel, ChannelStore
from app_ingestion import ingest
from app_workbench import AdvancedStudioWindow


class CleanPlotWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window=AdvancedStudioWindow()
        self.window.resize(1280,900);self.window.show();self.app.processEvents()

    def tearDown(self):
        self.window.close();self.app.processEvents()

    def channel(self,name,x,y):
        return self.window.store.add(Channel(name,x,y,unit='V',coordinate_unit='min'))

    def test_one_value_table_retains_every_split_when_selecting_another_graph(self):
        first=self.channel('First',[0,1,2,3],[0,10,20,30])
        second=self.channel('Short sensor',[1,2],[100,200])
        ws=self.window.dashboard;ws.set_layout('Vertical split')
        one,two=ws.visible_panes();one.bind([first.id]);two.bind([second.id]);ws.link()
        one.setXRange(0,3,padding=0)
        one.cursor_lines[0].setValue(1);one.cursor_lines[1].setValue(3)
        self.window._readouts()
        self.assertEqual(self.window.readout.rowCount(),2)
        ids=[self.window.readout.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole) for row in range(2)]
        row=ids.index(second.id)
        self.assertEqual(self.window.readout.item(row,2).text(),'100')
        self.assertEqual(self.window.readout.item(row,3).text(),'Unknown')
        self.window.readout.setCurrentCell(row,0)
        ws.set_active(two);self.window._readouts()
        self.assertEqual(self.window.readout.rowCount(),2)
        self.assertIn('All time graphs',self.window.cursor_caption.text())
        self.assertIn('Short sensor',self.window.interval_card.text())
        self.assertEqual(self.window.readout.item(self.window.readout.currentRow(),0).data(QtCore.Qt.ItemDataRole.UserRole),second.id)

    def test_mouse_values_from_other_graph_do_not_move_shared_cursors(self):
        first=self.channel('Fast',[0,1,2],[10,20,30])
        second=self.channel('Slow',[0,2],[100,200])
        ws=self.window.dashboard;ws.set_layout('Vertical split')
        one,two=ws.visible_panes();one.bind([first.id]);two.bind([second.id]);ws.link()
        self.window._readouts()
        before=[line.value() for line in one.cursor_lines]
        self.window.hover_values(ws,{'x':1,'coordinate_unit':'min','values':[
            {'channel':first.id,'y':20.,'x':1.,'index':1,'available':True,'color':'#00D2FF'},
            {'channel':second.id,'y':100.,'x':0.,'index':0,'available':True,'color':'#FF9F1C'}]})
        cells={self.window.readout.item(row,0).data(QtCore.Qt.ItemDataRole.UserRole):self.window.readout.item(row,9).text() for row in range(2)}
        self.assertEqual(cells,{first.id:'20',second.id:'100'})
        self.assertEqual([line.value() for line in one.cursor_lines],before)
        self.window.hover_values(ws,None)
        self.assertTrue(all(self.window.readout.item(row,9).text()=='—' for row in range(2)))

    def test_simple_primary_toolbar_keeps_tools_in_expandable_menu(self):
        primary=[action.text() for action in self.window.main_toolbar.actions() if action.isVisible()]
        self.assertIn('Open Data Files',primary)
        self.assertIn('Compare Selected Signals',primary)
        self.assertIn('Analyse Selected Signals',primary)
        self.assertNotIn('Compare Two Signals',primary)
        self.assertNotIn('Calculate Channel',primary)
        self.assertIn(self.window.signal_comparison.action,self.window.secondary_tools_menu.actions())
        self.assertIn(self.window.parameter_analysis.action,self.window.secondary_tools_menu.actions())
        layout_action=next(action for action in self.window.secondary_tools_menu.actions() if isinstance(action,QtWidgets.QWidgetAction) and action.defaultWidget() is self.window.layout_combo)
        self.assertIsNotNone(layout_action)
        self.window.secondary_tools_menu.popup(self.window.mapToGlobal(QtCore.QPoint(300,100)))
        self.app.processEvents()
        self.assertTrue(self.window.layout_combo.isVisible())
        self.window.secondary_tools_menu.close()

    def test_add_graph_is_blank_and_channels_are_ready_immediately_after_import(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'wrapped-clock.csv'
            path.write_text('datetime,Probe\n"=""2026-01-01 10:00:00.123""",3\n"=""2026-01-01 10:00:01.456""",4\n',encoding='utf-8')
            store=ChannelStore();ingest(store,path)
            with patch.object(self.window,'review_tdms_import',return_value=True):self.window.finish_import(store)
        self.app.processEvents()
        self.assertFalse(self.window.docks['Data Portal'].visibleRegion().isEmpty())
        initial=self.window.dashboard.visible_count()
        self.window.graph_controls.add_action.trigger();self.app.processEvents()
        self.assertEqual(self.window.dashboard.visible_count(),initial+1)
        self.assertEqual(self.window.dashboard.active.ids,[])
        self.assertTrue(all(channel.coordinate_unit=='min' for channel in self.window.store.channels.values()))
        self.assertEqual(len(self.window.store.channels),1)
