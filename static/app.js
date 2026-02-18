(function () {
    // --- Onboarding ---
    const onboardingOverlay = document.getElementById('onboarding-overlay');
    const onboardingPermissions = document.getElementById('onboarding-permissions');
    const onboardingModels = document.getElementById('onboarding-models');
    const onboardingContinueBtn = document.getElementById('onboarding-continue-btn');
    const onboardingSkipBtn = document.getElementById('onboarding-skip-btn');
    let onboardingPollTimer = null;
    let onboardingVisible = false;

    const CHECK_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
    const WARNING_SVG = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>';
    const SPINNER_SVG = '<svg width="12" height="12" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg>';

    function renderPermissionItem(key, perm) {
        var item = document.createElement('div');
        item.className = 'onboarding-item' + (perm.granted ? ' granted' : '');

        var iconClass = perm.granted ? 'granted' : (perm.required ? 'pending' : 'optional');
        var icon = perm.granted ? CHECK_SVG : WARNING_SVG;
        var statusText = perm.granted ? 'Granted' : (perm.required ? 'Required' : 'Optional');
        var statusClass = perm.granted ? '' : (perm.required ? 'pending' : '');

        var actionHtml = '';
        if (!perm.granted) {
            if (key === 'microphone' && perm.not_determined) {
                actionHtml = '<button class="onboarding-grant-btn" data-action="request-mic">Allow</button>';
            } else {
                actionHtml = '<button class="onboarding-grant-btn" data-url="' + perm.settings_url + '">Open Settings</button>';
            }
        }

        item.innerHTML =
            '<div class="onboarding-status-icon ' + iconClass + '">' + icon + '</div>' +
            '<div class="onboarding-item-info">' +
                '<div class="onboarding-item-name">' + perm.name + '</div>' +
                '<div class="onboarding-item-desc">' + perm.description + '</div>' +
                '<div class="onboarding-item-status ' + statusClass + '">' + statusText + '</div>' +
            '</div>' +
            actionHtml;

        return item;
    }

    function renderModelItem(key, model) {
        var item = document.createElement('div');
        item.className = 'onboarding-item' + (model.ready ? ' granted' : '');

        var iconClass, icon, statusText, statusClass;
        if (model.ready) {
            iconClass = 'granted';
            icon = CHECK_SVG;
            statusText = 'Ready';
            statusClass = '';
        } else {
            var st = model.status || 'loading';
            if (st === 'downloading') {
                iconClass = 'loading';
                icon = SPINNER_SVG;
                statusText = model.message || 'Downloading...';
                statusClass = 'loading';
            } else if (st === 'error') {
                iconClass = 'pending';
                icon = WARNING_SVG;
                statusText = model.message || 'Error';
                statusClass = 'pending';
            } else {
                iconClass = 'loading';
                icon = SPINNER_SVG;
                statusText = model.message || 'Loading...';
                statusClass = 'loading';
            }
        }

        item.innerHTML =
            '<div class="onboarding-status-icon ' + iconClass + '">' + icon + '</div>' +
            '<div class="onboarding-item-info">' +
                '<div class="onboarding-item-name">' + model.name + '</div>' +
                '<div class="onboarding-item-desc">' + model.description + '</div>' +
                '<div class="onboarding-item-status ' + statusClass + '">' + statusText + '</div>' +
            '</div>';

        return item;
    }

    function updateOnboarding(data) {
        onboardingPermissions.innerHTML = '';
        var permOrder = ['microphone', 'accessibility', 'screen_recording'];
        for (var i = 0; i < permOrder.length; i++) {
            var key = permOrder[i];
            var perm = data.permissions[key];
            if (perm) {
                onboardingPermissions.appendChild(renderPermissionItem(key, perm));
            }
        }

        onboardingModels.innerHTML = '';
        var modelKeys = Object.keys(data.models);
        for (var j = 0; j < modelKeys.length; j++) {
            onboardingModels.appendChild(renderModelItem(modelKeys[j], data.models[modelKeys[j]]));
        }

        // Wire action buttons
        onboardingPermissions.querySelectorAll('.onboarding-grant-btn').forEach(function (btn) {
            btn.onclick = async function (e) {
                e.stopPropagation();
                var url = btn.dataset.url;
                var action = btn.dataset.action;
                if (action === 'request-mic') {
                    await fetch('/api/permissions/request-microphone', { method: 'POST' });
                } else if (url) {
                    await fetch('/api/permissions/open-settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url }),
                    });
                }
            };
        });

        // Enable Continue when all required permissions granted AND whisper ready
        var allRequiredGranted = permOrder.every(function (k) {
            var p = data.permissions[k];
            return !p || !p.required || p.granted;
        });
        var whisperReady = data.models.whisper && data.models.whisper.ready;
        onboardingContinueBtn.disabled = !(allRequiredGranted && whisperReady);
    }

    async function pollOnboarding() {
        try {
            var resp = await fetch('/api/permissions');
            var data = await resp.json();

            if (data.onboarding_complete) {
                var micOk = data.permissions.microphone && data.permissions.microphone.granted;
                var accOk = data.permissions.accessibility && data.permissions.accessibility.granted;
                if (micOk && accOk) {
                    hideOnboarding();
                    return;
                }
            }

            if (!onboardingVisible) {
                showOnboarding();
            }
            updateOnboarding(data);
        } catch (e) {
            // Server not ready yet
        }
    }

    function showOnboarding() {
        onboardingVisible = true;
        onboardingOverlay.classList.remove('hidden');
        if (!onboardingPollTimer) {
            onboardingPollTimer = setInterval(pollOnboarding, 2000);
        }
    }

    function hideOnboarding() {
        onboardingVisible = false;
        onboardingOverlay.classList.add('hidden');
        if (onboardingPollTimer) {
            clearInterval(onboardingPollTimer);
            onboardingPollTimer = null;
        }
    }

    async function dismissOnboarding() {
        await fetch('/api/permissions/dismiss-onboarding', { method: 'POST' });
        hideOnboarding();
    }

    onboardingContinueBtn.addEventListener('click', dismissOnboarding);
    onboardingSkipBtn.addEventListener('click', dismissOnboarding);

    // Kick off onboarding check
    pollOnboarding();

    // --- Main App ---
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
        isRecording = false;
        const elapsed = Date.now() - recordStartTime;
        if (elapsed < MIN_RECORD_MS) {
            // Wait until minimum time has passed, then stop
            setTimeout(() => {
                ws.send(JSON.stringify({ action: 'stop' }));
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

    // --- Segmented Control ---
    document.querySelectorAll('.segment').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.segment').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.mode-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.mode + '-mode').classList.add('active');
        });
    });

    // --- Settings: Hotkey ---
    const hotkeyBtn = document.getElementById('hotkey-capture-btn');
    const hotkeyDisplay = document.getElementById('hotkey-display');
    const hotkeyResetBtn = document.getElementById('hotkey-reset-btn');
    let capturingHotkey = false;
    let capturePollId = null;

    async function loadHotkey() {
        try {
            const resp = await fetch('/api/settings/hotkey');
            const data = await resp.json();
            hotkeyDisplay.textContent = data.display || 'Right Option';
        } catch (e) { /* ignore */ }
    }

    async function saveHotkey(serialized) {
        try {
            const resp = await fetch('/api/settings/hotkey', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: serialized }),
            });
            const data = await resp.json();
            if (data.ok) {
                hotkeyDisplay.textContent = data.display;
            } else {
                hotkeyDisplay.textContent = 'Invalid key';
                setTimeout(loadHotkey, 1500);
            }
        } catch (e) {
            hotkeyDisplay.textContent = 'Error';
            setTimeout(loadHotkey, 1500);
        }
    }

    async function startCapture() {
        capturingHotkey = true;
        hotkeyBtn.classList.add('capturing');
        hotkeyDisplay.textContent = 'Press any key...';

        // Tell backend to start pynput key capture
        await fetch('/api/settings/hotkey/capture', { method: 'POST' });

        // Poll for captured key
        capturePollId = setInterval(async () => {
            try {
                const resp = await fetch('/api/settings/hotkey/capture');
                const data = await resp.json();
                if (data.captured) {
                    clearInterval(capturePollId);
                    capturePollId = null;
                    capturingHotkey = false;
                    hotkeyBtn.classList.remove('capturing');
                    saveHotkey(data.key);
                }
            } catch (e) { /* ignore */ }
        }, 100);

        // Timeout after 10 seconds
        setTimeout(() => {
            if (capturingHotkey) {
                clearInterval(capturePollId);
                capturePollId = null;
                capturingHotkey = false;
                hotkeyBtn.classList.remove('capturing');
                fetch('/api/settings/hotkey/capture', { method: 'DELETE' });
                loadHotkey();
            }
        }, 10000);
    }

    hotkeyBtn.addEventListener('click', () => {
        if (!capturingHotkey) startCapture();
    });

    hotkeyResetBtn.addEventListener('click', () => {
        saveHotkey('alt_r');
    });

    // Start disabled
    setMicDisabled(true);
    connect();
    loadHistory(false);
    loadHotkey();
})();
