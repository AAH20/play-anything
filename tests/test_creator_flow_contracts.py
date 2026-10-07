"""Focused source checks for the Creator's connection state transitions."""

from pathlib import Path
import unittest


CREATOR_JS = Path(__file__).resolve().parents[1] / "play_anything" / "creator.js"


class CreatorConnectionStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CREATOR_JS.read_text(encoding="utf-8")

    def test_mode_change_invalidates_connection_from_other_mode(self):
        self.assertIn("if(state.connection&&state.connection.mode!==mode){state.connection=null;", self.source)

    def test_failed_endpoint_check_clears_secret_and_marks_connection_inactive(self):
        self.assertIn("if(mode==='endpoint')$('connection-status').textContent='No verified endpoint.", self.source)
        self.assertIn("finally {$('api-key').value='';}", self.source)

    def test_successful_handoff_and_endpoint_keep_explicit_status(self):
        self.assertIn("'Handoff ready'", self.source)
        self.assertIn("state.connection.status+(state.connection.model?' · '+state.connection.model:'')", self.source)


if __name__ == "__main__":
    unittest.main()
