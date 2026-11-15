import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "recorder"))
import server


def pcm(seconds):
    return (np.random.default_rng(1).standard_normal(int(seconds * server.RATE)) * 3000).astype("<i2")


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "recordings" / "session"
        server.open_session(self.directory, "desk microphone")

    def test_a_two_minute_take_is_saved_losslessly(self):
        audio = pcm(120)
        session = server.save_clip(self.directory, 0, audio.tobytes())
        clip = session["clips"][0]
        self.assertEqual(clip["seconds"], 120)
        decoded, rate = sf.read(self.directory / clip["file"], dtype="int16")
        self.assertEqual(rate, 16000)
        self.assertTrue(np.array_equal(decoded, audio))
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), session)

    def test_a_take_longer_than_its_limit_is_refused(self):
        limit = server.TAKES[2]["max_seconds"]
        with self.assertRaises(ValueError):
            server.save_clip(self.directory, 2, pcm(limit + 5).tobytes())

    def test_saving_again_keeps_the_first_take(self):
        first = server.save_clip(self.directory, 0, pcm(2).tobytes())
        again = server.save_clip(self.directory, 0, pcm(3).tobytes())
        self.assertEqual(again, first)

    def test_redo_keeps_the_original_aside(self):
        server.save_clip(self.directory, 0, pcm(2).tobytes())
        archive = Path(self.tmp.name) / "retakes"
        session = server.retake_clip(self.directory, 0, archive)
        self.assertEqual(session["clips"], [])
        self.assertEqual(len(list((archive / "session").glob("*.flac"))), 1)
        self.assertEqual(len(server.save_clip(self.directory, 0, pcm(3).tobytes())["clips"]), 1)


if __name__ == "__main__":
    unittest.main()
