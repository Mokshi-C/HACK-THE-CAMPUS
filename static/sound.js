// Cyber Sound Synthesizer using Web Audio API
const CyberSound = {
    ctx: null,

    init() {
        if (!this.ctx) {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        }
    },

    playTick() {
        this.init();
        if (this.ctx.state === 'suspended') this.ctx.resume();
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, this.ctx.currentTime);
        gain.gain.setValueAtTime(0.02, this.ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + 0.05);

        osc.start();
        osc.stop(this.ctx.currentTime + 0.05);
    },

    playSuccess() {
        this.init();
        if (this.ctx.state === 'suspended') this.ctx.resume();
        const now = this.ctx.currentTime;
        this.playTone(523.25, now, 0.1); // C5
        this.playTone(659.25, now + 0.1, 0.1); // E5
        this.playTone(783.99, now + 0.2, 0.12); // G5
        this.playTone(1046.50, now + 0.32, 0.3); // C6
    },

    playError() {
        this.init();
        if (this.ctx.state === 'suspended') this.ctx.resume();
        const now = this.ctx.currentTime;
        this.playTone(140, now, 0.12, 'sawtooth');
        this.playTone(100, now + 0.12, 0.25, 'sawtooth');
    },

    playVictory() {
        this.init();
        if (this.ctx.state === 'suspended') this.ctx.resume();
        const now = this.ctx.currentTime;
        const scale = [523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77, 1046.50];
        scale.forEach((freq, index) => {
            this.playTone(freq, now + index * 0.12, 0.1);
        });
        // Chord at the end
        this.playTone(1046.50, now + 8 * 0.12, 0.8, 'triangle');
        this.playTone(1318.51, now + 8 * 0.12, 0.8, 'sine');
    },

    playTone(freq, time, duration, type = 'sine') {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.type = type;
        osc.frequency.setValueAtTime(freq, time);
        gain.gain.setValueAtTime(0.08, time);
        gain.gain.exponentialRampToValueAtTime(0.0001, time + duration);

        osc.start(time);
        osc.stop(time + duration);
    }
};

// Hook into keyboard events to simulate typing noises on inputs
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        CyberSound.playTick();
    }
});
