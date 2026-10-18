"""Same-unit traces keep their individual identity across selection changes."""
import unittest
from PySide6 import QtWidgets
from app_channel_store import Channel,ChannelStore
from app_plot_workspace import PlotPane
from app_trace_colors import channel_colors


class TraceColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_valves_have_distinct_matching_legend_colors_and_stable_rebind(self):
        store=ChannelStore()
        channels=[store.add(Channel(name,[0,1,2],[0,1,0],unit='state')) for name in ['Inlet Valve','Drain Valve','Heater']]
        pane=PlotPane(store);pane.bind([c.id for c in channels]);pane.show();self.app.processEvents()
        colors=[pane.curves[c.id][1].pen.color().name() for c in channels]
        self.assertEqual(len(set(colors)),3);self.assertTrue(pane.legend.isVisible())
        self.assertEqual(len(pane.legend.items),3)
        for (sample,label),color,c in zip(pane.legend.items,colors,channels):
            self.assertEqual(sample.item.opts['pen'].color().name(),color);self.assertEqual(label.text,c.name)
        pane.bind([channels[2].id]);self.assertEqual(pane.curves[channels[2].id][1].pen.color().name(),colors[2])
        pane.bind([c.id for c in channels]);self.assertEqual([pane.curves[c.id][1].pen.color().name() for c in channels],colors)
        pane.dark=False;pane.bind([c.id for c in channels])
        self.assertEqual(pane.legend.opts['labelTextColor'],'#182033')
        pane.close()
    def test_custom_color_and_saved_metadata_survive_other_file_removal(self):
        store=ChannelStore();a=store.add(Channel('A',[0],[1]));b=store.add(Channel('B',[0],[1],attributes={'plot_style':{'color':'#123456'}}))
        first=channel_colors(store);self.assertEqual(first[b.id],'#123456')
        del store.channels[b.id];self.assertEqual(channel_colors(store)[a.id],first[a.id]);self.assertEqual(a.attributes['trace_color'],first[a.id])
