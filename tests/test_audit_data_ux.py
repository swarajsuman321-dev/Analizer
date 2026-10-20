"""Approved everyday-data contracts: source identity, selection and recovery."""
import unittest
import os
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from PySide6 import QtCore, QtWidgets, QtTest
from app_channel_store import Channel, ChannelStore, Dataset
from app_channel_identity import dataset_aliases, channel_label, channel_details
from app_channel_portal import ChannelPortal
from app_compact_forms import CollapsibleHelp, ElidedComboBox, choose_item


def make_store():
    store=ChannelStore()
    a=Dataset('Recording with a very long name from laboratory A.csv',pd.DataFrame({'raw':[1,2]}),r'C:\Lab A\recording.csv')
    b=Dataset('Recording with a very long name from laboratory B.csv',pd.DataFrame({'raw':[3,4]}),r'C:\Lab B\recording.csv')
    store.datasets.update({a.id:a,b.id:b})
    channels=[]
    for ds in (a,b):
        for name in ('Pressure','Temperature'):
            channels.append(store.add(Channel(name,[0,1],[1,2],dataset_id=ds.id,source=ds.source)))
    return store,a,b,channels


class SourceIdentityTests(unittest.TestCase):
    def test_short_unique_source_labels_preserve_originals(self):
        store,a,b,channels=make_store();aliases=dataset_aliases(store)
        self.assertNotEqual(aliases[a.id],aliases[b.id])
        self.assertLess(len(aliases[a.id]),35)
        self.assertNotEqual(channel_label(store,channels[0]),channel_label(store,channels[2]))
        self.assertIn(a.name,channel_details(store,channels[0]))
        self.assertIn(a.source,channel_details(store,channels[0]))
        self.assertEqual(channels[0].name,'Pressure')
        del store.datasets[b.id]
        store.channels={c.id:c for c in channels[:2]}
        self.assertEqual(channel_label(store,channels[0]),'Pressure')
        self.assertIn(aliases[a.id].split(' [')[0],channel_label(store,channels[0],True))

    def test_removal_recovers_transitive_dependencies_order_and_metadata(self):
        store,a,b,channels=make_store();unrelated=channels[2]
        child=store.add(Channel('Derived',[0,1],[4,5],dataset_id=b.id,parents=[channels[0].id],attributes={'nested':{'value':1}}))
        grandchild=store.add(Channel('Second derived',[0,1],[7,8],parents=[child.id]))
        local=store.add(Channel('Source-local derived',[0,1],[3,4],dataset_id=a.id,parents=[channels[0].id]))
        old_order=list(store.channels);plan=store.removal_plan([a.id])
        self.assertEqual(plan['dependent_ids'],{child.id,grandchild.id,local.id})
        snap=store.removal_snapshot([a.id]);child.attributes['nested']['value']=9
        a.frame.iloc[0,0]=99
        removed=store.remove_datasets([a.id]);self.assertEqual(removed,set(snap.channel_ids))
        self.assertIs(store.channels[unrelated.id],unrelated)
        extra=store.add(Channel('Later import',[0],[5]));events=[];store.observe(events.append)
        store.restore_removal(snap)
        self.assertEqual(list(store.channels),old_order+[extra.id])
        self.assertEqual(store.channels[child.id].attributes['nested']['value'],1)
        self.assertEqual(store.datasets[a.id].frame.iloc[0,0],1)
        self.assertIs(store.channels[channels[0].id].x,channels[0].x)
        self.assertFalse(store.channels[channels[0].id].x.flags.writeable)
        self.assertEqual(len(events),1);self.assertIs(store.channels[unrelated.id],unrelated)

    def test_undo_collision_is_atomic_and_clear_includes_generated_data(self):
        store,a,b,channels=make_store();generated=store.add(Channel('Generated',[0],[1]))
        snapshot=store.removal_snapshot([a.id]);store.remove_datasets([a.id]);store.add(channels[0])
        before=list(store.channels)
        with self.assertRaisesRegex(ValueError,'identity'):
            store.restore_removal(snapshot)
        self.assertEqual(list(store.channels),before);self.assertNotIn(a.id,store.datasets)
        self.assertIn(generated.id,store.removal_snapshot([],clear_all=True).channel_ids)

    def test_truncated_alias_collisions_and_generated_sources_stay_distinct(self):
        store,a,b,channels=make_store()
        # Differences beyond the shortened prefix must not merge source labels.
        a.name='A shared recording prefix '+('long '*20)+'left.csv'
        b.name='A shared recording prefix '+('long '*20)+'right.csv'
        generated_dataset=Dataset('Generated.csv',pd.DataFrame(),r'C:\Lab C\Generated.csv')
        store.datasets[generated_dataset.id]=generated_dataset
        recorded=store.add(Channel('Pressure',[0],[3],dataset_id=generated_dataset.id))
        calculated=store.add(Channel('Pressure',[0],[5]))
        aliases=dataset_aliases(store)
        self.assertEqual(len(set(value.casefold() for value in aliases.values())),len(aliases))
        self.assertIn('…',aliases[a.id]);self.assertNotEqual(aliases[a.id],aliases[b.id])
        self.assertNotEqual(channel_label(store,recorded),channel_label(store,calculated))
        self.assertIn(a.name,channel_details(store,channels[0]))
        self.assertEqual(a.name,'A shared recording prefix '+('long '*20)+'left.csv')


class DataUXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store,self.a,self.b,self.channels=make_store();self.portal=ChannelPortal(self.store)
        self.requests=[]
        def apply(ids,shown):
            self.requests.append((set(ids),shown))
            self.portal.set_visible((self.portal.visible_ids|set(ids)) if shown else (self.portal.visible_ids-set(ids)))
        self.portal.visibilityRequested.connect(apply)

    def tearDown(self):self.portal.close();self.app.processEvents()

    def test_file_checkbox_and_filtered_results_have_explicit_different_scope(self):
        self.portal.search.setText('Pressure')
        self.assertIn('1/2 results',self.portal.dataset_roots[self.a.id].text(0))
        self.portal.filter_buttons[self.a.id].click()
        self.assertEqual(self.portal.visible_ids,{self.channels[0].id})
        self.assertEqual(self.portal.filter_buttons[self.a.id].text(),'Deselect Results')
        root=self.portal.dataset_roots[self.a.id];root.setCheckState(0,QtCore.Qt.CheckState.Checked)
        self.assertEqual(self.portal.visible_ids,{c.id for c in self.channels[:2]})
        self.assertFalse(self.portal.visible_ids & {c.id for c in self.channels[2:]})
        self.portal.filter_buttons[self.a.id].click()
        self.assertEqual(self.portal.visible_ids,{self.channels[1].id})
        self.assertIn('1 plotted',root.text(0))

    def test_invalid_regex_has_no_stale_results_and_recovers_without_plot_change(self):
        self.portal.set_visible([self.channels[0].id]);self.portal.regex.setChecked(True)
        self.portal.search.setText('[')
        self.assertFalse(self.portal.filter_valid);self.assertFalse(self.portal.search_error.isHidden())
        self.assertIn('turn off',self.portal.search_error.text())
        for id,root in self.portal.dataset_roots.items():
            self.assertEqual(root.childCount(),0);self.assertFalse(self.portal.filter_buttons[id].isEnabled())
        self.assertEqual(self.portal.visible_ids,{self.channels[0].id})
        self.portal.search.setText('Temperature')
        self.assertTrue(self.portal.filter_valid);self.assertTrue(self.portal.search_error.isHidden())
        self.assertEqual(self.portal.filtered_ids[self.a.id],[self.channels[1].id])
        self.portal.search.clear();self.assertEqual(len(self.portal.filtered_ids[self.a.id]),2)

    def test_cursor_and_reference_forms_keep_help_optional_and_long_sources_accessible(self):
        from app_studio_tools import StudioTools
        window=QtWidgets.QMainWindow();window.store=self.store
        channel=self.channels[0];channel.name='Long source parameter '+('very descriptive '*30)
        locks=[];pane=SimpleNamespace(ids=[c.id for c in self.channels],cursor_locks=[None,None],lock_cursor=lambda index,id:locks.append((index,id)))
        window.active_workspace=SimpleNamespace(active=pane);window.guard=lambda fn:fn()
        tools=StudioTools.__new__(StudioTools);QtCore.QObject.__init__(tools,window)
        tools.window=window;tools.dialogs=[];tools.reference_settings={}
        try:
            dialog=tools.cursor_lock_dialog();self.app.processEvents()
            help_widget=dialog.findChild(CollapsibleHelp)
            self.assertTrue(help_widget.details.isHidden());self.assertLess(dialog.width(),620)
            selectors=dialog.findChildren(ElidedComboBox);self.assertEqual(len(selectors),2)
            selectors[0].setCurrentIndex(1);self.assertIn(channel.name,selectors[0].toolTip())
            self.assertIn(self.a.source,selectors[0].accessibleDescription())
            help_widget.button.setFocus();QtTest.QTest.keyClick(help_widget.button,QtCore.Qt.Key.Key_Space)
            self.app.processEvents();self.assertTrue(help_widget.button.isChecked())
            self.assertFalse(help_widget.details.isHidden());self.assertLess(dialog.width(),620)
            help_widget.button.click();self.assertTrue(help_widget.details.isHidden())
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Apply').click()
            self.assertEqual(locks,[(0,channel.id),(1,None)])
            reference=tools.reference_units();self.app.processEvents()
            self.assertTrue(reference.findChild(CollapsibleHelp).details.isHidden())
            self.assertLess(reference.width(),620)
            reference.close()
        finally:
            for dialog in list(tools.dialogs):dialog.close()
            window.close();self.app.processEvents()

    def test_tdms_review_keeps_help_optional_and_warnings_validation_visible(self):
        from app_tdms_templates import ParameterReview
        channel=self.channels[0];original='Long technical TDMS parameter '+('source '*50)
        channel.attributes.update(original_name=original,tdms_template_key='/Group/'+original)
        dialog=ParameterReview([channel],warning='Saved template is invalid; review this parameter again.')
        try:
            dialog.show();dialog.resize(650,450);self.app.processEvents()
            helper=dialog.findChild(CollapsibleHelp)
            self.assertTrue(helper.details.isHidden());self.assertTrue(dialog.warning.isVisible())
            self.assertIn('review this parameter',dialog.warning.text())
            self.assertEqual(dialog.table.item(0,0).text(),original)
            self.assertIn(original,dialog.table.item(0,0).toolTip())
            dialog.table.item(0,1).setText('');dialog.accept()
            self.assertTrue(dialog.isVisible());self.assertIn('display name',dialog.error.text())
            helper.button.setFocus();QtTest.QTest.keyClick(helper.button,QtCore.Qt.Key.Key_Space)
            self.app.processEvents();self.assertFalse(helper.details.isHidden())
            save=next(button for button in dialog.findChildren(QtWidgets.QPushButton) if button.text()=='Save template and load')
            self.assertTrue(save.isVisible());self.assertTrue(dialog.rect().contains(save.mapTo(dialog,save.rect().center())))
            helper.button.click();dialog.table.item(0,1).setText('Reviewed pressure')
            self.assertEqual(next(iter(dialog.entries().values()))['name'],'Reviewed pressure')
            self.assertEqual(channel.attributes['original_name'],original)
        finally:dialog.close();self.app.processEvents()

    def test_long_item_chooser_is_compact_keyboard_accessible_and_returns_full_value(self):
        long='Technical source column '+('precise metadata '*50);observed={}
        def accept_selection():
            dialog=self.app.activeModalWidget();field=dialog.findChild(ElidedComboBox)
            field.setFocus();QtTest.QTest.keyClick(field,QtCore.Qt.Key.Key_End)
            observed.update(width=dialog.width(),text=field.currentText(),tip=field.toolTip(),accessible=field.accessibleDescription())
            QtTest.QTest.keyClick(dialog,QtCore.Qt.Key.Key_Return)
        QtCore.QTimer.singleShot(0,accept_selection)
        value,accepted=choose_item(None,'Choose source','Source recording', ['First',long])
        self.assertTrue(accepted);self.assertEqual(value,long);self.assertLess(observed['width'],620)
        self.assertEqual(observed['text'],long);self.assertEqual(observed['tip'],long);self.assertEqual(observed['accessible'],long)
        QtCore.QTimer.singleShot(0,lambda:QtTest.QTest.keyClick(self.app.activeModalWidget(),QtCore.Qt.Key.Key_Escape))
        value,accepted=choose_item(None,'Choose source','Source recording',[long])
        self.assertFalse(accepted);self.assertEqual(value,long)


class DatasetRecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'ANALIZER_SETTINGS_DIR':self.temp.name,'ANALIZER_OUTPUT_DIR':self.temp.name});self.env.start()
        from app_workbench import AdvancedStudioWindow
        self.window=AdvancedStudioWindow();self.window.show();self.app.processEvents()
        store,self.a,self.b,self.channels=make_store()
        for channel in self.channels:channel.coordinate_unit='min'
        self.window.store.datasets.update(store.datasets)
        with self.window.store.batch():
            for channel in self.channels:self.window.store.add(channel)

    def tearDown(self):
        self.window.close();self.app.processEvents();self.env.stop();self.temp.cleanup()

    def test_undo_recovers_bindings_locks_and_preserves_later_metadata(self):
        window=self.window;source=self.channels[0];other=self.channels[2]
        derived=window.store.add(Channel('Derived pressure',[0,1],[3,4],coordinate_unit='min',dataset_id=self.a.id,parents=[source.id],recipe={'operation':'scale','factor':3}))
        window.dashboard.assign([source.id,other.id]);window.comparison.assign([derived.id])
        pane=window.dashboard.active;pane.lock_cursor(0,source.id)
        saved_lock=dict(pane.cursor_locks[0]);saved_bindings=dict(pane.bindings)
        listeners=len(window.store.listeners)
        window.drop_recordings([self.a.id]);self.assertNotIn(source.id,window.store.channels)
        window.store.update(other.id,attributes={'later':{'preserve':True}})
        extra=window.store.add(Channel('New calculated value',[0,1],[7,8],coordinate_unit='min',dataset_id=self.b.id))
        window.dashboard.assign([extra.id]);window.studio.options['title']='Title edited after removal'
        window.undo_recording_removal();self.app.processEvents()
        self.assertIn(source.id,window.store.channels);self.assertIn(derived.id,window.comparison.active.ids)
        self.assertIn(extra.id,window.dashboard.active.ids)
        self.assertEqual(window.dashboard.active.cursor_locks[0],saved_lock)
        for id,binding in saved_bindings.items():self.assertEqual(window.dashboard.active.bindings[id],binding)
        self.assertEqual(window.store.channels[other.id].attributes['later'],{'preserve':True})
        self.assertEqual(window.studio.options['title'],'Title edited after removal')
        self.assertEqual(len(window.store.listeners),listeners)
        self.assertFalse(window.undo_removal_action.isEnabled())

    def test_local_derived_work_is_previewed_before_user_removal(self):
        window=self.window;source=self.channels[0]
        derived=window.store.add(Channel('Unsaved derived result',[0,1],[3,4],coordinate_unit='min',dataset_id=self.a.id,parents=[source.id]))
        with patch.object(QtWidgets.QMessageBox,'exec',return_value=QtWidgets.QMessageBox.StandardButton.No) as question:
            window.request_drop_recordings([self.a.id])
        self.assertEqual(question.call_count,1)
        self.assertIn(source.id,window.store.channels);self.assertIn(derived.id,window.store.channels)

    def test_undo_keeps_new_second_pane_layout_bindings_and_cursor_lock(self):
        window=self.window;source=self.channels[0];other=self.channels[2]
        window.dashboard.assign([source.id]);window.drop_recordings([self.a.id])
        window.dashboard.set_layout('Vertical split')
        window.dashboard.set_active(window.dashboard.panes[1]);window.dashboard.assign([other.id])
        second=window.dashboard.active;second.lock_cursor(1,other.id)
        saved_lock=dict(second.cursor_locks[1]);saved_binding=second.bindings[other.id]
        window.undo_recording_removal();self.app.processEvents()
        self.assertEqual(window.dashboard.layout_name,'Vertical split')
        self.assertIn(source.id,window.dashboard.panes[0].ids)
        self.assertIn(other.id,window.dashboard.panes[1].ids)
        self.assertEqual(window.dashboard.panes[1].bindings[other.id],saved_binding)
        self.assertEqual(window.dashboard.panes[1].cursor_locks[1],saved_lock)
        self.assertIs(window.dashboard.active,window.dashboard.panes[1])

    def test_undo_keeps_later_lock_in_an_existing_empty_second_pane(self):
        window=self.window;source=self.channels[0];other=self.channels[2]
        window.dashboard.set_layout('Vertical split');window.dashboard.assign([source.id])
        window.drop_recordings([self.a.id]);window.dashboard.set_active(window.dashboard.panes[1])
        window.dashboard.assign([other.id]);window.dashboard.active.lock_cursor(1,other.id)
        saved_lock=dict(window.dashboard.active.cursor_locks[1])
        window.undo_recording_removal();self.app.processEvents()
        self.assertIn(source.id,window.dashboard.panes[0].ids)
        self.assertIn(other.id,window.dashboard.panes[1].ids)
        self.assertEqual(window.dashboard.panes[1].cursor_locks[1],saved_lock)

    def test_structured_metadata_retains_nested_values_and_rejects_invalid_advanced_edits(self):
        window=self.window;channel=self.channels[0]
        window.store.update(channel.id,attributes={'nested':{'reference':[1,2]},'raw_text':'source'})
        window.selection([channel.id])
        self.assertTrue(window.prop_attrs.isHidden())
        row=window.prop_metadata.rowCount();window.prop_metadata.insertRow(row)
        window.prop_metadata.setItem(row,0,QtWidgets.QTableWidgetItem('lab note'))
        window.prop_metadata.setItem(row,1,QtWidgets.QTableWidgetItem('Reviewed at bench'))
        with patch.object(window.portal,'selected',return_value=[channel.id]):window.apply_properties()
        attrs=window.store.channels[channel.id].attributes
        self.assertEqual(attrs['nested'],{'reference':[1,2]});self.assertEqual(attrs['lab note'],'Reviewed at bench')
        window.metadata_advanced.setChecked(True);self.app.processEvents()
        window.prop_attrs.setPlainText('[]');window.metadata_advanced.setChecked(False)
        self.assertTrue(window.metadata_advanced.isChecked());self.assertIn('JSON object',window.statusBar().currentMessage())
        self.assertEqual(window.store.channels[channel.id].attributes['nested'],{'reference':[1,2]})
        window.prop_attrs.setPlainText('{"nested": {"reference": [3, 4]}, "reviewed": true}')
        window.metadata_advanced.setChecked(False);self.assertFalse(window.metadata_advanced.isChecked())
        self.assertEqual(window.structured_metadata(),{'nested':{'reference':[3,4]},'reviewed':True})

    def test_tools_menu_header_and_context_share_actions_and_shortcuts(self):
        window=self.window;tools=window.studio
        for command,action in tools.navigation_menu_actions.items():
            self.assertIs(action,window.dashboard.navigation_actions[command])
        window.dashboard.assign([self.channels[0].id]);tools.navigation_menu_actions['x'].trigger()
        self.assertTrue(window.dashboard.navigation_actions['x'].isChecked())
        window.tabs.setCurrentIndex(1);self.app.processEvents()
        for command,action in tools.navigation_menu_actions.items():
            self.assertIs(action,window.comparison.navigation_actions[command])
        self.assertEqual(window.dashboard.navigation_actions['x'].shortcut().toString(),'')
        self.assertEqual(window.comparison.navigation_actions['x'].shortcut().toString(),'Ctrl+1')
        window.tabs.setCurrentIndex(0);self.app.processEvents()
        self.assertTrue(tools.navigation_menu_actions['x'].isChecked())


if __name__=='__main__':unittest.main()
