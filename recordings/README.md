# Recordings

One directory per recording session. Each holds the takes as mono 16 kHz
16-bit FLAC and a `manifest.json` listing them:

```json
{
  "id": "2026-11-15",
  "capture": {"sample_rate": 16000, "channels": 1, "echo_cancellation": true,
              "noise_suppression": false, "auto_gain_control": true},
  "notes": "MacBook microphone, office, TV two metres away",
  "clips": [
    {"index": 0, "take": "talk-quiet", "prompt": "Talk for a minute or two in a quiet room.",
     "file": "01-talk-quiet.flac", "seconds": 94.2, "bytes": 1503211, "sha256": "…"}
  ]
}
```
