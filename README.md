# voice-recordings

Real voice recordings for testing the Arya voice stack, and the recorder that
makes them. The recorder is the one from Keryxion's wakewords repository, set
up for long takes instead of short prompts.

## Record

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python recorder/server.py --notes "MacBook microphone, office, TV two metres away"
```

Open <http://127.0.0.1:8792>. Click **Record**, wait for **Recording**, talk,
then **Stop & save**. Each take stops by itself at its time limit. The takes
are listed in `takes.json`:

| Take | What to do | Limit |
|---|---|---|
| `talk-quiet` | Talk for a minute or two in a quiet room | 3:00 |
| `talk-over-tv` | The same with the TV or music on | 3:00 |
| `room-only` | Say nothing; leave the TV or music playing | 1:00 |

Takes are saved in `recordings/<session>/` as mono 16 kHz 16-bit FLAC with a
`manifest.json`; see [recordings/README.md](recordings/README.md). The session
is today's date unless you pass `--session <name>`, and running the recorder
again resumes it. Commit the session directory when you are happy with it.

The microphone settings match the Arya clients: echo cancellation and automatic
gain on, noise suppression off. Check which microphone the browser has selected
before recording.

Saved takes appear in a list with playback and a waveform and spectrogram.
**Redo** frees a take for re-recording and moves the original to the ignored
`work/retakes/` directory. A failed save keeps its audio in the tab for retry.

### From another device

Browsers only allow microphone capture from another machine over HTTPS, so
serve with a certificate for the host name:

```sh
.venv/bin/python recorder/server.py --public-host recorder.example.net \
  --cert work/tls/cert.pem --key work/tls/key.pem
```

Open `https://recorder.example.net:8792/?key=<key>` using the key in
`work/recorder.token`. Every page and request needs the key or the cookie it
sets, and requests are not logged.

## Use the recordings in tests

Tests in other repositories read the files from a checkout of this one. Decode
with any FLAC reader; `manifest.json` gives each take's id, file, length and
SHA-256.

## Test the recorder

```sh
.venv/bin/python -m unittest discover -s tests -v
```
