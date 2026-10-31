"""User-created blank graphs retain order, proportions and source bindings."""
import unittest
import numpy as np
from PySide6 import QtWidgets
from app_channel_store import Channel,ChannelStore
from app_plot_workspace import PlotWorkspace


class FlexibleGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_add_blank_reorder_resize_restore_remove_without_deleting_sources(self):
        store=ChannelStore();a=store.add(Channel('A',np.arange(5.),np.arange(5.),coordinate_unit='min'))
        b=store.add(Channel('B',np.arange(5.),np.arange(5.),coordinate_unit='min'))
        work=PlotWorkspace(store);work.show()
        try:
            first=work.active;first.bind([a.id]);second=work.add_graph()
            self.assertEqual(second.ids,[]);self.assertIs(work.active,second)
            work.assign([b.id]);third=work.add_graph()
            self.assertEqual(len(work.visible_panes()),3);self.assertEqual(third.ids,[])
            work.move_graph(second,-1)
            self.assertEqual([p.ids for p in work.visible_panes()],[[b.id],[a.id],[]])
            work.set_pane_proportions(rows=[2.,1.,3.])
            old_panes=list(work.panes)
            saved=work.state();work.restore(saved)
            self.assertTrue(all(pane._callbacks_stopped for pane in old_panes))
            self.assertEqual([p.ids for p in work.visible_panes()],[[b.id],[a.id],[]])
            self.assertEqual(work.layout_proportions[work.layout_name]['rows'],[2.,1.,3.])
            work.remove_graph(work.panes[0]);self.app.processEvents()
            self.assertEqual(len(work.visible_panes()),2)
            self.assertIn(b.id,store.channels)
            work.remove_graph(work.panes[0]);work.remove_graph(work.active)
            self.assertEqual(len(work.visible_panes()),1)
        finally:work.close();self.app.processEvents()

    def test_adding_graph_never_reveals_channels_from_a_hidden_layout(self):
        store=ChannelStore();c=store.add(Channel('Retained',np.arange(3.),np.arange(3.)))
        work=PlotWorkspace(store)
        try:
            work.set_layout('Vertical split');work.panes[1].bind([c.id])
            work.set_layout('Single');added=work.add_graph()
            self.assertEqual(added.ids,[])
            self.assertTrue(any(p.ids==[c.id] for p in work.panes[2:]))
        finally:work.close();self.app.processEvents()

    def test_maximum_graph_count_and_rejection_preserve_existing_layout(self):
        work=PlotWorkspace(ChannelStore())
        try:
            work.set_layout('32 graphs')
            self.assertEqual(len(work.visible_panes()),32)
            before=work.state()
            with self.assertRaisesRegex(ValueError,'32 graphs'):work.add_graph()
            self.assertEqual(work.state(),before)
        finally:work.close();self.app.processEvents()

    def test_close_stops_pending_plot_and_alignment_callbacks(self):
        store=ChannelStore();c=store.add(Channel('Synthetic',[0,1,2],[0,1,0]))
        work=PlotWorkspace(store)
        try:
            work.assign([c.id]);work.queue_canvas_alignment()
            self.assertTrue(work._canvas_alignment_timer.isActive())
            work.close()
            self.assertFalse(work._canvas_alignment_timer.isActive())
            self.assertTrue(all(pane._closing and not pane.timer.isActive() for pane in work.panes))
            work.queue_canvas_alignment()
            self.assertFalse(work._canvas_alignment_timer.isActive())
        finally:
            work.close();work.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
