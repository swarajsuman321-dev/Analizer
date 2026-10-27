from copy import deepcopy
import unittest

from app_metadata_merge import merge_metadata_edits


class MetadataMergeTests(unittest.TestCase):
    def test_new_color_survives_unrelated_and_nested_user_edits(self):
        base = {'plot_style': {'color': '#58b6ff', 'width': 1}, 'note': 'before'}
        current = {'plot_style': {'color': '#cc1144', 'width': 1}, 'note': 'before', 'external': True}
        edited = {'plot_style': {'color': '#58b6ff', 'width': 2}, 'note': 'after'}
        original = deepcopy((base, edited, current))
        result = merge_metadata_edits(base, edited, current)
        self.assertEqual(result, {'plot_style': {'color': '#cc1144', 'width': 2}, 'note': 'after', 'external': True})
        self.assertEqual((base, edited, current), original)

    def test_new_style_color_is_retained_when_user_adds_another_style_field(self):
        self.assertEqual(merge_metadata_edits({}, {'plot_style': {'width': 2}}, {'plot_style': {'color': '#cc1144'}}),
                         {'plot_style': {'color': '#cc1144', 'width': 2}})

    def test_user_changes_and_deletions_take_precedence(self):
        base = {'plot_style': {'color': 'old', 'width': 1}, 'note': 'remove'}
        edited = {'plot_style': {'color': 'user'}}
        current = {'plot_style': {'color': 'external', 'width': 2}, 'note': 'new', 'keep': 1}
        self.assertEqual(merge_metadata_edits(base, edited, current), {'plot_style': {'color': 'user'}, 'keep': 1})

    def test_external_removals_remain_removed_without_a_user_edit(self):
        self.assertEqual(merge_metadata_edits({'old': 1}, {'old': 1}, {}), {})

    def test_invalid_top_level_is_rejected(self):
        for values in [(None, {}, {}), ({}, [], {}), ({}, {}, 'bad')]:
            with self.assertRaises(ValueError):
                merge_metadata_edits(*values)


if __name__ == '__main__':
    unittest.main()
