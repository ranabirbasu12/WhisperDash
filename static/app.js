(function () {
    const micBtn = document.getElementById('mic-btn');
    const micLabel = document.getElementById('mic-label');
    const resultText = document.getElementById('result-text');
    const toast = document.getElementById('toast');
    const modelStatus = document.getElementById('model-status');
    const latencyEl = document.getElementById('latency');

    let ws = null;
    let isRecording = false;

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws`);

        ws.onopen = () => {
            ws.send(JSON.stringify({ action: 'status' }));
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);

            if (msg.type === 'status') {
                if (msg.status === 'recording') {
                    micBtn.classList.add('recording');
                    micBtn.classList.remove('transcribing');
                    micLabel.textContent = 'Recording...';
                } else if (msg.status === 'transcribing') {
                    micBtn.classList.remove('recording');
                    micBtn.classList.add('transcribing');
                    micLabel.textContent = 'Transcribing...';
                }
            } else if (msg.type === 'result') {
                micBtn.classList.remove('recording', 'transcribing');
                micLabel.textContent = 'Hold to Record';
                resultText.textContent = msg.text;
                latencyEl.textContent = msg.latency + 's';
                showToast();
                isRecording = false;
            } else if (msg.type === 'model_status') {
                if (msg.ready) {
                    modelStatus.innerHTML = '<span class="dot ready"></span> Ready';
                } else {
                    modelStatus.innerHTML = '<span class="dot loading"></span> Loading model...';
                }
            }
        };

        ws.onclose = () => {
            setTimeout(connect, 1000);
        };
    }

    function showToast() {
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 2000);
    }

    // Push-to-talk: mousedown = start, mouseup = stop
    micBtn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (isRecording) return;
        isRecording = true;
        ws.send(JSON.stringify({ action: 'start' }));
    });

    micBtn.addEventListener('mouseup', (e) => {
        e.preventDefault();
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (!isRecording) return;
        ws.send(JSON.stringify({ action: 'stop' }));
    });

    micBtn.addEventListener('mouseleave', (e) => {
        if (!isRecording) return;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({ action: 'stop' }));
    });

    connect();
})();
