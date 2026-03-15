/**
 * Ambient Audio System — location-based background sounds.
 *
 * Uses Web Audio API to create layered atmospheric audio:
 *   宴会厅: jazz + fireplace + rain
 *   书房: clock ticking + pen scratching + rain (muffled)
 *   花园: rain (loud) + crickets + wind
 *   酒窖: water drips + distant hum + echo
 *   走廊: footsteps echo + flickering lights + wind
 *
 * Tension affects the mix: high tension adds heartbeat + lowers other sounds.
 *
 * Since we can't ship audio files easily, we generate tones using Web Audio API
 * oscillators and noise generators to simulate ambient sounds.
 */

type AmbientPreset = {
  label: string;
  layers: Array<{
    type: "noise" | "tone" | "pulse";
    frequency?: number;
    gain: number;
    filterFreq?: number;
  }>;
};

const PRESETS: Record<string, AmbientPreset> = {
  宴会厅: {
    label: "宴会厅",
    layers: [
      { type: "noise", gain: 0.03, filterFreq: 800 },     // Soft crowd murmur
      { type: "tone", frequency: 220, gain: 0.008 },       // Low warm hum (fireplace)
      { type: "noise", gain: 0.015, filterFreq: 400 },     // Rain outside (muffled)
    ],
  },
  书房: {
    label: "书房",
    layers: [
      { type: "pulse", frequency: 1, gain: 0.02 },         // Clock ticking
      { type: "noise", gain: 0.01, filterFreq: 300 },      // Silence with faint rain
      { type: "tone", frequency: 60, gain: 0.005 },        // Desk lamp buzz
    ],
  },
  花园: {
    label: "花园",
    layers: [
      { type: "noise", gain: 0.06, filterFreq: 2000 },     // Rain (loud, outdoor)
      { type: "tone", frequency: 3500, gain: 0.003 },      // Crickets (high pitch)
      { type: "noise", gain: 0.02, filterFreq: 200 },      // Wind
    ],
  },
  酒窖: {
    label: "酒窖",
    layers: [
      { type: "pulse", frequency: 0.5, gain: 0.015 },      // Water drips
      { type: "tone", frequency: 45, gain: 0.012 },        // Deep unsettling hum
      { type: "noise", gain: 0.008, filterFreq: 150 },     // Eerie silence
    ],
  },
  走廊: {
    label: "走廊",
    layers: [
      { type: "noise", gain: 0.02, filterFreq: 500 },      // Echo-y silence
      { type: "tone", frequency: 100, gain: 0.006 },       // Flickering light buzz
      { type: "noise", gain: 0.01, filterFreq: 250 },      // Distant wind
    ],
  },
};

// Heartbeat layer for high tension
const HEARTBEAT = { type: "pulse" as const, frequency: 1.2, gain: 0.04 };

export class AmbientAudioManager {
  private ctx: AudioContext | null = null;
  private nodes: AudioNode[] = [];
  private gainNode: GainNode | null = null;
  private currentScene: string = "";
  private masterVolume: number = 0.5;
  private heartbeatNode: OscillatorNode | null = null;
  private heartbeatGain: GainNode | null = null;

  start() {
    if (this.ctx) return;
    this.ctx = new AudioContext();
  }

  setVolume(vol: number) {
    this.masterVolume = Math.max(0, Math.min(1, vol));
    if (this.gainNode) {
      this.gainNode.gain.setTargetAtTime(this.masterVolume, this.ctx!.currentTime, 0.3);
    }
  }

  switchScene(sceneName: string, tension: number = 20) {
    // Find matching preset
    const key = Object.keys(PRESETS).find((k) => sceneName.includes(k)) || "宴会厅";
    if (key === this.currentScene && this.nodes.length > 0) {
      // Same scene — just update tension effects
      this.updateTension(tension);
      return;
    }
    this.currentScene = key;
    this.stopAll();
    this.start();

    const preset = PRESETS[key];
    if (!preset || !this.ctx) return;

    // Master gain
    this.gainNode = this.ctx.createGain();
    this.gainNode.gain.value = this.masterVolume;
    this.gainNode.connect(this.ctx.destination);

    // Build layers
    for (const layer of preset.layers) {
      this.createLayer(layer);
    }

    this.updateTension(tension);
  }

  updateTension(tension: number) {
    if (!this.ctx || !this.gainNode) return;

    // High tension: add heartbeat, lower ambient
    if (tension > 60) {
      if (!this.heartbeatNode) {
        this.heartbeatGain = this.ctx.createGain();
        this.heartbeatGain.gain.value = 0;
        this.heartbeatGain.connect(this.gainNode);

        this.heartbeatNode = this.ctx.createOscillator();
        this.heartbeatNode.type = "sine";
        this.heartbeatNode.frequency.value = HEARTBEAT.frequency;
        this.heartbeatNode.connect(this.heartbeatGain);
        this.heartbeatNode.start();
      }
      // Heartbeat gets louder as tension increases
      const heartbeatVol = ((tension - 60) / 40) * HEARTBEAT.gain;
      this.heartbeatGain!.gain.setTargetAtTime(heartbeatVol, this.ctx.currentTime, 0.5);
    } else if (this.heartbeatNode) {
      this.heartbeatGain!.gain.setTargetAtTime(0, this.ctx.currentTime, 0.5);
    }
  }

  private createLayer(layer: AmbientPreset["layers"][0]) {
    if (!this.ctx || !this.gainNode) return;

    const layerGain = this.ctx.createGain();
    layerGain.gain.value = layer.gain;

    if (layer.type === "noise") {
      // White noise → filter for ambient sounds
      const bufferSize = this.ctx.sampleRate * 2;
      const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {
        data[i] = Math.random() * 2 - 1;
      }
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.loop = true;

      const filter = this.ctx.createBiquadFilter();
      filter.type = "lowpass";
      filter.frequency.value = layer.filterFreq || 1000;

      source.connect(filter);
      filter.connect(layerGain);
      layerGain.connect(this.gainNode);
      source.start();
      this.nodes.push(source, filter, layerGain);

    } else if (layer.type === "tone") {
      const osc = this.ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = layer.frequency || 220;
      osc.connect(layerGain);
      layerGain.connect(this.gainNode);
      osc.start();
      this.nodes.push(osc, layerGain);

    } else if (layer.type === "pulse") {
      // LFO-modulated tone for rhythmic sounds (clock, drips, heartbeat)
      const osc = this.ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = 80;

      const lfo = this.ctx.createOscillator();
      lfo.type = "square";
      lfo.frequency.value = layer.frequency || 1;

      const lfoGain = this.ctx.createGain();
      lfoGain.gain.value = layer.gain;

      lfo.connect(lfoGain);
      lfoGain.connect(osc.frequency);
      osc.connect(layerGain);
      layerGain.connect(this.gainNode);
      osc.start();
      lfo.start();
      this.nodes.push(osc, lfo, lfoGain, layerGain);
    }
  }

  stopAll() {
    for (const node of this.nodes) {
      try {
        if (node instanceof OscillatorNode || node instanceof AudioBufferSourceNode) {
          node.stop();
        }
        node.disconnect();
      } catch {
        // Already stopped
      }
    }
    this.nodes = [];
    if (this.heartbeatNode) {
      try { this.heartbeatNode.stop(); } catch { /* */ }
      this.heartbeatNode = null;
      this.heartbeatGain = null;
    }
  }

  dispose() {
    this.stopAll();
    if (this.ctx) {
      void this.ctx.close();
      this.ctx = null;
    }
  }
}
