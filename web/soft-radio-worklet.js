/* BlueNode Soft Radio Phase A: receive-only G.711 mu-law playback. */
class BlueNodeUlawPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.position = 0;
    this.started = false;
    this.levelCounter = 0;
    this.maximumSamples = 8000 * 0.24;
    this.targetSamples = 8000 * 0.06;
    this.port.onmessage = event => {
      if (!(event.data instanceof ArrayBuffer)) return;
      const encoded = new Uint8Array(event.data);
      const decoded = new Float32Array(encoded.length);
      for (let index = 0; index < encoded.length; index++) decoded[index] = this.decode(encoded[index]);
      this.samples.push(...decoded);
      if (this.samples.length > this.maximumSamples)
        this.samples.splice(0, this.samples.length - this.targetSamples);
    };
  }

  decode(value) {
    value = (~value) & 0xff;
    const sign = value & 0x80;
    const exponent = (value >> 4) & 0x07;
    const mantissa = value & 0x0f;
    let magnitude = ((mantissa << 3) + 0x84) << exponent;
    magnitude -= 0x84;
    return (sign ? -magnitude : magnitude) / 32768;
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    const ratio = 8000 / sampleRate;
    let peak = 0;
    if (!this.started && this.samples.length >= this.targetSamples) this.started = true;
    if (!this.started) {
      output.fill(0);
      return true;
    }
    for (let index = 0; index < output.length; index++) {
      const sourceIndex = Math.floor(this.position);
      const nextIndex = sourceIndex + 1;
      if (nextIndex < this.samples.length) {
        const fraction = this.position - sourceIndex;
        output[index] = this.samples[sourceIndex] * (1 - fraction) +
          this.samples[nextIndex] * fraction;
        peak = Math.max(peak, Math.abs(output[index]));
        this.position += ratio;
      } else {
        output[index] = 0;
        this.started = false;
      }
    }
    const consumed = Math.floor(this.position);
    if (consumed > 0) {
      this.samples.splice(0, consumed);
      this.position -= consumed;
    }
    if (++this.levelCounter >= 8) {
      this.port.postMessage({type:'level', value:Math.min(1, peak * 2)});
      this.levelCounter = 0;
    }
    return true;
  }
}

registerProcessor('bluenode-ulaw-player', BlueNodeUlawPlayer);
