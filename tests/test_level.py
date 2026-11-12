import unittest

try:
    import numpy as np

    from raccontami_sync.narrate_worker import level
except ImportError as e:  # numpy is part of the voice environments, not of the GitHub check
    raise unittest.SkipTest(f"needs numpy: {e}")

SR = 24000


def speech(amplitude: float) -> "np.ndarray":
    """A second of a tone as a stand-in for speech, with half a second of silence on each side."""
    tone = amplitude * np.sin(2 * np.pi * 180 * np.arange(SR) / SR)
    return np.concatenate([np.zeros(SR // 2), tone, np.zeros(SR // 2)]).astype(np.float32)


def loudness(wav) -> float:
    return float(np.sqrt(np.mean(wav[SR // 2:SR // 2 + SR] ** 2)))


class LevelTest(unittest.TestCase):
    def test_a_quiet_and_a_loud_voice_come_out_equally_loud(self):
        self.assertAlmostEqual(loudness(level(speech(0.05), SR)), loudness(level(speech(0.6), SR)), places=3)

    def test_the_pauses_do_not_count(self):
        longer_pause = np.concatenate([np.zeros(SR * 3, dtype=np.float32), speech(0.2)])
        self.assertAlmostEqual(loudness(level(speech(0.2), SR)), float(np.sqrt(np.mean(level(longer_pause, SR)[SR * 3 + SR // 2:SR * 3 + SR // 2 + SR] ** 2))), places=3)

    def test_a_burst_far_above_the_voice_is_rounded_off(self):
        spike = speech(0.02)
        spike[SR] = 0.9
        self.assertLessEqual(float(np.max(np.abs(level(spike, SR)))), 0.8 + 1e-6)

    def test_rounding_off_bursts_does_not_change_the_loudness(self):
        spike = speech(0.2)
        spike[SR] = 0.9
        self.assertAlmostEqual(loudness(level(speech(0.2), SR)), loudness(level(spike, SR)), places=2)

    def test_silence_stays_silence(self):
        self.assertEqual(0.0, float(np.max(np.abs(level(np.zeros(SR, dtype=np.float32), SR)))))


if __name__ == "__main__":
    unittest.main()
