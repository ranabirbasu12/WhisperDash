// static/bar.js
(function () {
    const bar = document.getElementById('bar');
    const tooltip = document.getElementById('tooltip');
    const cancelBtn = document.getElementById('cancel-btn');
    const stopBtn = document.getElementById('stop-btn');
    const canvas = document.getElementById('waveform');
    const ctx = canvas.getContext('2d');
    const barIdle = document.querySelector('.bar-idle');
    const warningEl = document.getElementById('bar-warning');

    let ws = null;
    let currentState = 'idle';
    let amplitudes = [];
    const NUM_BARS = 20;
    let animFrameId = null;
    let warningTimeout = null;

    // Initialize amplitude array
    for (let i = 0; i < NUM_BARS; i++) amplitudes.push(0);

    function setState(state) {
        currentState = state;
        bar.className = 'bar ' + state;
        if (state === 'recording') {
            startWaveformAnimation();
        } else {
            stopWaveformAnimation();
        }
    }

    function drawWaveform() {
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        const barWidth = w / NUM_BARS * 0.6;
        const gap = w / NUM_BARS * 0.4;
        const centerY = h / 2;

        for (let i = 0; i < NUM_BARS; i++) {
            // Scale RMS (typically 0.01-0.15) to visual range 0-1
            const amp = Math.min((amplitudes[i] || 0) * 8, 1);
            const barHeight = Math.max(2, amp * h * 0.9);
            const x = i * (barWidth + gap) + gap / 2;
            const y = centerY - barHeight / 2;

            // Gradient from green to white
            const intensity = Math.min(amp * 2, 1);
            const r = Math.round(100 + intensity * 155);
            const g = Math.round(200 + intensity * 55);
            const b = Math.round(100 + intensity * 155);
            ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barHeight, 2);
            ctx.fill();
        }

        animFrameId = requestAnimationFrame(drawWaveform);
    }

    function startWaveformAnimation() {
        if (animFrameId) return;
        drawWaveform();
    }

    function stopWaveformAnimation() {
        if (animFrameId) {
            cancelAnimationFrame(animFrameId);
            animFrameId = null;
        }
    }

    function pushAmplitude(value) {
        amplitudes.shift();
        amplitudes.push(value);
    }

    function showWarning(message) {
        warningEl.textContent = message;
        warningEl.classList.remove('hidden');
        if (warningTimeout) clearTimeout(warningTimeout);
        warningTimeout = setTimeout(() => {
            warningEl.classList.add('hidden');
            warningTimeout = null;
        }, 5000);
    }

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws/bar`);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'state') {
                setState(msg.state);
            } else if (msg.type === 'amplitude') {
                pushAmplitude(msg.value);
            } else if (msg.type === 'warning') {
                showWarning(msg.message);
            } else if (msg.type === 'hotkey') {
                tooltip.textContent = 'Hold ' + msg.display + ' to dictate';
            }
        };

        ws.onclose = () => {
            setTimeout(connect, 1000);
        };
    }

    // Click idle bar to start recording
    barIdle.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'start' }));
        }
    });

    // Stop button
    stopBtn.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'stop' }));
        }
    });

    // Cancel button
    cancelBtn.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'cancel' }));
        }
    });

    // Tooltip on hover (idle state only)
    barIdle.addEventListener('mouseenter', () => {
        if (currentState === 'idle') tooltip.classList.remove('hidden');
    });
    barIdle.addEventListener('mouseleave', () => {
        tooltip.classList.add('hidden');
    });

    connect();
})();
