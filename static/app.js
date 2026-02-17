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
                loadHistory(false);
                isRecording = false;
            } else if (msg.type === 'error') {
                micBtn.classList.remove('recording', 'transcribing');
                micLabel.textContent = 'Hold to Record';
                resultText.textContent = msg.message;
                isRecording = false;
                if (fileTranscribing) {
                    fileTranscribing = false;
                    transcribeBtn.disabled = !filePathInput.value.trim() || !modelReady;
                    fileProgress.classList.add('hidden');
                }
            } else if (msg.type === 'model_status') {
                updateModelState(msg);
            } else if (msg.type === 'file_status') {
                fileTranscribing = true;
                transcribeBtn.disabled = true;
                fileResult.classList.add('hidden');
                fileProgress.classList.remove('hidden');
                fileProgressMsg.textContent = msg.message || 'Transcribing file...';
            } else if (msg.type === 'file_result') {
                fileTranscribing = false;
                transcribeBtn.disabled = !filePathInput.value.trim() || !modelReady;
                fileProgress.classList.add('hidden');
                fileResult.classList.remove('hidden');
                fileResultText.textContent = 'Transcription saved (' + msg.latency + 's)';
                fileOutputPath.textContent = msg.output_path;
                loadHistory(false);
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

    // --- File Transcription ---
    const filePathInput = document.getElementById('file-path');
    const browseBtn = document.getElementById('browse-btn');
    const transcribeBtn = document.getElementById('transcribe-btn');
    const fileProgress = document.getElementById('file-progress');
    const fileProgressMsg = document.getElementById('file-progress-msg');
    const fileResult = document.getElementById('file-result');
    const fileResultText = document.getElementById('file-result-text');
    const fileOutputPath = document.getElementById('file-output-path');
    let fileTranscribing = false;

    filePathInput.addEventListener('input', () => {
        transcribeBtn.disabled = !filePathInput.value.trim() || !modelReady || fileTranscribing;
    });

    browseBtn.addEventListener('click', async () => {
        const resp = await fetch('/api/browse-file');
        const data = await resp.json();
        if (data.path) {
            filePathInput.value = data.path;
            transcribeBtn.disabled = !modelReady || fileTranscribing;
        }
    });

    transcribeBtn.addEventListener('click', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (!filePathInput.value.trim() || fileTranscribing) return;
        ws.send(JSON.stringify({ action: 'transcribe_file', path: filePathInput.value.trim() }));
    });

    // --- History ---
    const historyList = document.getElementById('history-list');
    const historySearch = document.getElementById('history-search');
    const loadMoreBtn = document.getElementById('load-more-btn');
    let historyOffset = 0;
    const HISTORY_PAGE = 50;
    let totalHistory = 0;

    function formatTime(isoString) {
        const d = new Date(isoString);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function createHistoryEntry(entry) {
        const div = document.createElement('div');
        div.className = 'history-entry';
        div.innerHTML =
            '<span class="history-time">' + formatTime(entry.timestamp) + '</span>' +
            '<span class="history-text">' + escapeHtml(entry.text) + '</span>' +
            '<button class="history-copy-btn" aria-label="Copy">' +
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">' +
                    '<path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>' +
                '</svg>' +
            '</button>';
        div.querySelector('.history-copy-btn').addEventListener('click', () => {
            navigator.clipboard.writeText(entry.text);
            showToast();
        });
        return div;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async function loadHistory(append) {
        if (!append) {
            historyOffset = 0;
            historyList.innerHTML = '';
        }
        const resp = await fetch('/api/history?limit=' + HISTORY_PAGE + '&offset=' + historyOffset);
        const data = await resp.json();
        totalHistory = data.total;
        data.entries.forEach(e => historyList.appendChild(createHistoryEntry(e)));
        historyOffset += data.entries.length;
        loadMoreBtn.classList.toggle('hidden', historyOffset >= totalHistory);
    }

    async function searchHistory(query) {
        if (!query) {
            loadHistory(false);
            return;
        }
        historyList.innerHTML = '';
        const resp = await fetch('/api/history/search?q=' + encodeURIComponent(query));
        const data = await resp.json();
        data.entries.forEach(e => historyList.appendChild(createHistoryEntry(e)));
        loadMoreBtn.classList.add('hidden');
    }

    let searchTimeout = null;
    historySearch.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => searchHistory(historySearch.value.trim()), 300);
    });

    loadMoreBtn.addEventListener('click', () => loadHistory(true));

    // Periodically refresh history to pick up hotkey transcriptions
    setInterval(() => {
        if (!isRecording) loadHistory(false);
    }, 3000);

    // Start disabled
    setMicDisabled(true);
    connect();
    loadHistory(false);
})();
