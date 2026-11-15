"""Recorder for long voice takes. Saves each take once as lossless FLAC; no cloud audio transport."""

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse, datetime, hashlib, io, json, secrets, ssl, threading

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
RATE = 16000
TAKES = json.loads((ROOT / "takes.json").read_text())
# The microphone settings the Arya clients use; the page requests the same.
CAPTURE = {"sample_rate": RATE, "channels": 1, "echo_cancellation": True,
           "noise_suppression": False, "auto_gain_control": True}


def write_manifest(directory, session):
    pending = directory / "manifest.tmp.json"
    pending.write_text(json.dumps(session, indent=2) + "\n")
    pending.replace(directory / "manifest.json")


def open_session(directory, notes=""):
    """Create the session's manifest, or resume the one already there."""
    directory.mkdir(parents=True, exist_ok=True)
    if not (directory / "manifest.json").exists():
        write_manifest(directory, {"id": directory.name, "capture": CAPTURE, "notes": notes, "clips": []})
    return json.loads((directory / "manifest.json").read_text())


def save_clip(directory, index, payload):
    session = json.loads((directory / "manifest.json").read_text())
    if not 0 <= index < len(TAKES):
        raise ValueError("No such take")
    take = TAKES[index]
    if not RATE <= len(payload) <= RATE * 2 * (take["max_seconds"] + 1) or len(payload) % 2:
        raise ValueError(f"Expected 0.5–{take['max_seconds']} seconds of PCM16 mono at 16 kHz")
    if any(c["index"] == index for c in session["clips"]):
        return session  # a retry after a lost response never replaces a saved take
    pcm = np.frombuffer(payload, dtype="<i2")
    path = directory / f"{index + 1:02d}-{take['id']}.flac"
    pending = path.with_suffix(".tmp.flac")
    sf.write(pending, pcm, RATE, format="FLAC", subtype="PCM_16")
    decoded, rate = sf.read(pending, dtype="int16")
    if rate != RATE or not np.array_equal(decoded, pcm):
        pending.unlink(missing_ok=True)
        raise ValueError("Lossless audio verification failed")
    pending.replace(path)
    session["clips"].append({"index": index, "take": take["id"], "prompt": take["text"], "file": path.name,
                             "seconds": len(pcm) / RATE, "bytes": path.stat().st_size,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    session["clips"].sort(key=lambda c: c["index"])
    write_manifest(directory, session)
    return session


def retake_clip(directory, index, archive_root):
    """Free a take for re-recording; the original moves to the ignored archive, not the bin."""
    session = json.loads((directory / "manifest.json").read_text())
    clip = next((c for c in session["clips"] if c["index"] == index), None)
    if clip is None:
        raise ValueError("That take has no saved recording")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = archive_root / session["id"]
    archive.mkdir(parents=True, exist_ok=True)
    (directory / clip["file"]).rename(archive / f"{Path(clip['file']).stem}-{stamp}.flac")
    session["clips"] = [c for c in session["clips"] if c["index"] != index]
    write_manifest(directory, session)
    return session


def spectrogram_png(path):
    """Waveform plus log-frequency spectrogram of one saved take."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from scipy.signal import stft

    pcm, rate = sf.read(path)
    frequencies, times, spectrum = stft(pcm, rate, nperseg=512, noverlap=384)
    decibels = 20 * np.log10(np.maximum(np.abs(spectrum), 1e-6))
    figure = Figure(figsize=(9, 4), layout="constrained")
    wave, spec = figure.subplots(2, 1, sharex=True, height_ratios=[1, 2])
    wave.plot(np.arange(len(pcm)) / rate, pcm, linewidth=0.6)
    wave.set_ylim(-1, 1)
    wave.set_ylabel("Waveform")
    wave.grid(alpha=0.2)
    image = spec.pcolormesh(times, frequencies[1:], decibels[1:], shading="auto", cmap="magma", vmin=-90, vmax=-15)
    spec.set_yscale("log")
    spec.set_ylim(80, 8000)
    spec.set_ylabel("Frequency (Hz)")
    spec.set_xlabel("Time (seconds)")
    spec.set_xlim(0, len(pcm) / rate)
    figure.colorbar(image, ax=spec, label="Level (dBFS)")
    output = io.BytesIO()
    FigureCanvasAgg(figure).print_png(output)
    return output.getvalue()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8792)
    p.add_argument("--session", default=datetime.date.today().isoformat(),
                   help="Directory under recordings/; an existing session resumes (default: today's date)")
    p.add_argument("--notes", default="", help="Microphone/device, room, distance and background noise")
    p.add_argument("--public-host", help="Serve HTTPS on the network under this host name (requires --cert/--key)")
    p.add_argument("--cert", type=Path, help="TLS certificate for --public-host")
    p.add_argument("--key", type=Path, help="TLS private key for --public-host")
    p.add_argument("--token-file", type=Path, default=ROOT / "work/recorder.token",
                   help="Persistent network access key (network mode only)")
    args = p.parse_args()
    if bool(args.public_host) != bool(args.cert and args.key):
        p.error("--public-host requires --cert and --key, and they require --public-host")
    if args.public_host:
        # Browsers only allow microphone capture from other machines over HTTPS.
        # Every request needs this key; the URL carrying it is the only access path.
        args.token_file.parent.mkdir(parents=True, exist_ok=True)
        if not args.token_file.exists():
            args.token_file.write_text(secrets.token_urlsafe(24))
            args.token_file.chmod(0o600)
        token = args.token_file.read_text().strip()
    else:
        token = secrets.token_urlsafe(24)
    hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    if args.public_host:
        hosts.add(f"{args.public_host}:{args.port}")
    directory = ROOT / "recordings" / args.session
    if directory.parent != ROOT / "recordings":
        p.error("--session is one directory name")
    open_session(directory, args.notes)
    previews, retakes = ROOT / "work/previews" / args.session, ROOT / "work/retakes"
    lock = threading.Lock()
    largest = max(t["max_seconds"] for t in TAKES)

    class Handler(BaseHTTPRequestHandler):
        def send(self, data, status=200, kind="application/json", cookie=False):
            payload = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if cookie:
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Set-Cookie", f"recorder={token}; Secure; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *values):
            if not args.public_host:  # network URLs carry the access key
                super().log_message(format, *values)

        def authorized(self):
            if not args.public_host:
                return True
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            supplied = parse_qs(urlparse(self.path).query).get("key", [""])[0]
            return secrets.compare_digest(supplied, token) or (
                "recorder" in cookie and secrets.compare_digest(cookie["recorder"].value, token))

        def do_GET(self):
            if self.headers.get("Host") not in hosts:
                return self.send({"error": "Invalid host"}, 403)
            if not self.authorized():
                return self.send({"error": "Open the recorder link that includes its access key"}, 403)
            path = self.path.split("?")[0]
            if path == "/":
                page = (ROOT / "recorder/index.html").read_bytes().replace(b"__TOKEN__", token.encode())
                return self.send(page, kind="text/html; charset=utf-8", cookie=bool(args.public_host))
            if path == "/capture-worklet.js":
                return self.send((ROOT / "recorder/capture-worklet.js").read_bytes(), kind="application/javascript")
            if path == "/api/status":
                return self.send({"session": json.loads((directory / "manifest.json").read_text()), "takes": TAKES})
            if path.startswith("/api/audio/") or path.startswith("/api/spectrogram/"):
                try:
                    index = int(path.rsplit("/", 1)[1])
                    clips = json.loads((directory / "manifest.json").read_text())["clips"]
                    clip = next(c for c in clips if c["index"] == index)
                except (ValueError, StopIteration):
                    return self.send({"error": "Recording not found"}, 404)
                audio = directory / clip["file"]
                if path.startswith("/api/audio/"):
                    return self.send(audio.read_bytes(), kind="audio/flac")
                with lock:
                    preview = previews / (clip["file"] + ".png")
                    if not preview.exists() or preview.stat().st_mtime < audio.stat().st_mtime:
                        preview.parent.mkdir(parents=True, exist_ok=True)
                        preview.write_bytes(spectrogram_png(audio))
                return self.send(preview.read_bytes(), kind="image/png")
            return self.send({"error": "Not found"}, 404)

        def do_POST(self):
            if self.headers.get("Host") not in hosts:
                return self.send({"error": "Invalid host"}, 403)
            if not secrets.compare_digest(self.headers.get("X-Local-Token", ""), token):
                return self.send({"error": "Invalid local token"}, 403)
            path = self.path.split("?")[0]
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= RATE * 2 * (largest + 1):
                    raise ValueError("Recording too large")
                payload = self.rfile.read(size)
                index = int(path.rsplit("/", 1)[1])
                with lock:
                    if path.startswith("/api/clip/"):
                        return self.send(save_clip(directory, index, payload))
                    if path.startswith("/api/retake/"):
                        return self.send(retake_clip(directory, index, retakes))
                return self.send({"error": "Not found"}, 404)
            except Exception as e:
                return self.send({"error": str(e)}, 400)

    server = ThreadingHTTPServer(("0.0.0.0" if args.public_host else "127.0.0.1", args.port), Handler)
    if args.public_host:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        url = f"https://{args.public_host}:{args.port}/?key=<key> (access key in {args.token_file})"
    else:
        url = f"http://127.0.0.1:{args.port}"
    print(f"Open {url} — takes are saved in {directory}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
