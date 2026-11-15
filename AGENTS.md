# Repository instructions

This repository holds real voice recordings used to test the Arya voice stack,
and the recorder that makes them.

- Recordings are the repository owner's voice, published here with their permission.
- Store recordings as mono 16 kHz 16-bit FLAC under `recordings/<session>/`,
  with the session's `manifest.json`. Do not use lossy compression or reduce
  the sample precision.
- Do not edit, trim or re-encode a committed recording. Record a new session.
- Tests in other repositories read these files from a local checkout. Keep
  take ids in `takes.json` stable once recordings use them.
