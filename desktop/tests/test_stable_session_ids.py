import pathlib
import sys
import types
import unittest

DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_DIR))

from audio_service import AudioService, AudioItem


class StableSessionIdTests(unittest.TestCase):
    def setUp(self):
        self.audio = AudioService()

    def test_stable_ids_remain_unchanged_when_new_sessions_added(self):
        items_initial = [
            AudioItem(id=0, name="Chrome", volume=50, is_muted=False, _session_identifier="chrome_123"),
            AudioItem(id=0, name="Spotify", volume=80, is_muted=False, _session_identifier="spotify_456"),
        ]
        self.audio._assign_protocol_ids(items_initial, lambda x: x._session_identifier)
        
        chrome_id_1 = items_initial[0].id
        spotify_id_1 = items_initial[1].id
        
        self.assertGreater(chrome_id_1, 0)
        self.assertGreater(spotify_id_1, 0)
        self.assertNotEqual(chrome_id_1, spotify_id_1)

        # Now add Discord before Chrome
        items_with_new = [
            AudioItem(id=0, name="Discord", volume=90, is_muted=False, _session_identifier="discord_789"),
            AudioItem(id=0, name="Chrome", volume=50, is_muted=False, _session_identifier="chrome_123"),
            AudioItem(id=0, name="Spotify", volume=80, is_muted=False, _session_identifier="spotify_456"),
        ]
        self.audio._assign_protocol_ids(items_with_new, lambda x: x._session_identifier)

        discord_id = items_with_new[0].id
        chrome_id_2 = items_with_new[1].id
        spotify_id_2 = items_with_new[2].id

        # Verify Chrome and Spotify IDs did NOT change
        self.assertEqual(chrome_id_1, chrome_id_2)
        self.assertEqual(spotify_id_1, spotify_id_2)
        self.assertGreater(discord_id, 0)
        self.assertNotIn(discord_id, (chrome_id_1, spotify_id_1))

    def test_ids_are_bounded_7bit(self):
        items = [
            AudioItem(id=0, name=f"App_{i}", volume=50, is_muted=False, _session_identifier=f"app_{i}")
            for i in range(50)
        ]
        self.audio._assign_protocol_ids(items, lambda x: x._session_identifier)
        
        for item in items:
            self.assertGreaterEqual(item.id, 1)
            self.assertLessEqual(item.id, 127)

        # All IDs must be unique
        assigned_ids = [item.id for item in items]
        self.assertEqual(len(assigned_ids), len(set(assigned_ids)))


if __name__ == "__main__":
    unittest.main()
