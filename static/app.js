(function () {
    const micBtn = document.getElementById('mic-btn');
    const micLabel = document.getElementById('mic-label');
    const resultText = document.getElementById('result-text');
    const toast = document.getElementById('toast');
    const modelStatus = document.getElementById('model-status');
    const latencyEl = document.getElementById('latency');
    const progressContainer = document.getElementById('progress-container');
    const progressFill = document.getElementById('progress-fill');
    const progressMessage = document.getElementById('progress-message');

    let ws = null;
    let isRecording = false;
    let modelReady = false;
    let statusPollTimer = null;
    let recordStartTime = 0;
    const MIN_RECORD_MS = 300;

    function setMicDisabled(disabled) {
        if (disabled) {
            micBtn.classList.add('disabled');
            micLabel.textContent = 'Model loading...';
        } else {
            micBtn.classList.remove('disabled');
            micLabel.textContent = 'Hold to Record';
        }
    }

    function updateModelState(msg) {
        const status = msg.status || (msg.ready ? 'ready' : 'loading');
        const message = msg.message || '';

        modelReady = msg.ready;
        setMicDisabled(!modelReady);

        if (status === 'ready') {
            modelStatus.innerHTML = '<span class="dot ready"></span> Ready';
            progressContainer.classList.add('hidden');
            stopStatusPolling();
        } else if (status === 'downloading') {
            modelStatus.innerHTML = '<span class="dot downloading"></span> Downloading...';
            progressFill.className = 'progress-fill downloading';
            progressMessage.className = 'progress-message downloading';
            progressMessage.textContent = message || 'Downloading model...';
            progressContainer.classList.remove('hidden');
        } else if (status === 'loading') {
            modelStatus.innerHTML = '<span class="dot loading"></span> Loading...';
            progressFill.className = 'progress-fill loading';
            progressMessage.className = 'progress-message loading';
            progressMessage.textContent = message || 'Loading model into memory...';
            progressContainer.classList.remove('hidden');
        } else if (status === 'error') {
            modelStatus.innerHTML = '<span class="dot error"></span> Error';
            progressFill.className = 'progress-fill error';
            progressMessage.className = 'progress-message error';
            progressMessage.textContent = message || 'Failed to load model';
            progressContainer.classList.remove('hidden');
            stopStatusPolling();
        } else {
            modelStatus.innerHTML = '<span class="dot loading"></span> Initializing...';
            progressFill.className = 'progress-fill loading';
            progressMessage.className = 'progress-message';
            progressMessage.textContent = message || 'Initializing...';
            progressContainer.classList.remove('hidden');
        }
    }

    function pollStatus() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'status' }));
        }
    }

    function startStatusPolling() {
        if (statusPollTimer) return;
        statusPollTimer = setInterval(pollStatus, 1000);
    }

    function stopStatusPolling() {
        if (statusPollTimer) {
            clearInterval(statusPollTimer);
            statusPollTimer = null;
        }
    }

    function connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws`);

        ws.onopen = () => {
            pollStatus();
            startStatusPolling();
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
            } else if (msg.type === 'error') {
                micBtn.classList.remove('recording', 'transcribing');
                micLabel.textContent = 'Hold to Record';
                resultText.textContent = msg.message;
                isRecording = false;
            } else if (msg.type === 'model_status') {
                updateModelState(msg);
            }
        };

        ws.onclose = () => {
            stopStatusPolling();
            setTimeout(connect, 1000);
        };
    }

    function showToast() {
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 2000);
    }

    function stopRecording() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (!isRecording) return;
        const elapsed = Date.now() - recordStartTime;
        if (elapsed < MIN_RECORD_MS) {
            // Wait until minimum time has passed, then stop
            setTimeout(() => {
                if (isRecording) {
                    ws.send(JSON.stringify({ action: 'stop' }));
                }
            }, MIN_RECORD_MS - elapsed);
        } else {
            ws.send(JSON.stringify({ action: 'stop' }));
        }
    }

    // Push-to-talk: mousedown = start, mouseup = stop
    micBtn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (!modelReady) return;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (isRecording) return;
        isRecording = true;
        recordStartTime = Date.now();
        ws.send(JSON.stringify({ action: 'start' }));
    });

    micBtn.addEventListener('mouseup', (e) => {
        e.preventDefault();
        stopRecording();
    });

    micBtn.addEventListener('mouseleave', (e) => {
        stopRecording();
    });

    // Start disabled
    setMicDisabled(true);
    connect();
})();
