"""Release delivery must not place the full growing manual in GitHub's body field."""
from pathlib import Path
import unittest
from scripts.release_notes import release_notes
from app_version import VERSION


class ReleaseNotesTests(unittest.TestCase):
    def test_current_complete_manual_has_bounded_summary_and_manual_link(self):
        manual=(Path(__file__).resolve().parents[1]/f'manuals/v{VERSION}.md').read_text(encoding='utf-8')
        notes=release_notes(VERSION,manual)
        self.assertLess(len(notes.encode('utf-8')),16000)
        self.assertIn(f'v{VERSION}.md',notes)
        self.assertNotIn('## Quick start',notes)
    def test_missing_or_unbounded_summary_is_rejected(self):
        for manual in ('no changes heading','## Changes in this version\n','## Changes in this version\n'+'x'*12001):
            with self.assertRaises(ValueError):release_notes('1.0.0',manual)
