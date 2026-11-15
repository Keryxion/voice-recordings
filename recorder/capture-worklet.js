// Same raw PCM16 conversion/frame size as Arya's mic-worklet.js.
class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Int16Array(1280);
    this.n = 0;
  }
  process(inputs) {
    for (const s0 of inputs[0]?.[0] || []) {
      const s = Math.max(-1, Math.min(1, s0));
      this.frame[this.n++] = s < 0 ? s * 32768 : s * 32767;
      if (this.n === 1280) {
        const f = this.frame;
        this.port.postMessage(f, [f.buffer]);
        this.frame = new Int16Array(1280);
        this.n = 0;
      }
    }
    return true;
  }
}
registerProcessor("capture", Capture);
