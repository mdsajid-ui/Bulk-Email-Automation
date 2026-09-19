// Bulk Email Automator - Frontend Logic

let loadedRecipients = [];
let loadedAttachments = [];
let isSendingActive = false;
let eventSource = null;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    fetchCurrentAttachments();
    checkActiveTaskStatus();
});

// Tab Switching (File vs Paste)
function switchRecipientTab(tab) {
    const tabFileBtn = document.getElementById("tabFileBtn");
    const tabPasteBtn = document.getElementById("tabPasteBtn");
    const tabFileContent = document.getElementById("tabFileContent");
    const tabPasteContent = document.getElementById("tabPasteContent");

    if (tab === "file") {
        tabFileBtn.className = "pb-2.5 px-4 border-b-2 border-indigo-600 text-indigo-600 flex items-center space-x-2";
        tabPasteBtn.className = "pb-2.5 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 flex items-center space-x-2";
        tabFileContent.classList.remove("hidden");
        tabPasteContent.classList.add("hidden");
    } else {
        tabPasteBtn.className = "pb-2.5 px-4 border-b-2 border-indigo-600 text-indigo-600 flex items-center space-x-2";
        tabFileBtn.className = "pb-2.5 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 flex items-center space-x-2";
        tabPasteContent.classList.remove("hidden");
        tabFileContent.classList.add("hidden");
    }
}

// Recipient Upload Handlers
async function handleRecipientsFileUpload(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    updateRecipientCountBadge("Loading...", "bg-amber-100 text-amber-800");

    try {
        const res = await fetch("/api/upload-recipients", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            applyParsedRecipients(data);
        } else {
            alert("Error parsing file: " + (data.error || "Unknown error"));
            updateRecipientCountBadge("Error", "bg-rose-100 text-rose-800");
        }
    } catch (err) {
        alert("Upload failed: " + err.message);
        updateRecipientCountBadge("Error", "bg-rose-100 text-rose-800");
    }
}

async function handleRecipientsPaste() {
    const text = document.getElementById("pasteEmailsInput").value.trim();
    if (!text) {
        alert("Please paste at least one email address.");
        return;
    }

    const formData = new FormData();
    formData.append("paste_text", text);

    try {
        const res = await fetch("/api/upload-recipients", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            applyParsedRecipients(data);
        } else {
            alert("Error parsing emails: " + (data.error || "Unknown error"));
        }
    } catch (err) {
        alert("Parsing failed: " + err.message);
    }
}

function applyParsedRecipients(data) {
    loadedRecipients = data.recipients || [];
    const count = loadedRecipients.length;

    updateRecipientCountBadge(`${count} Valid Recipients`, "bg-emerald-100 text-emerald-800 border-emerald-200");
    document.getElementById("cardRecipientCount").textContent = count;
    document.getElementById("statTotal").textContent = count;

    // Show preview section
    const previewSection = document.getElementById("recipientsPreviewSection");
    previewSection.classList.remove("hidden");

    document.getElementById("recipientStatsText").textContent = 
        `Loaded ${count} valid recipients (${data.invalid_count || 0} invalid/duplicates skipped)`;

    // Render available tags
    const tagsContainer = document.getElementById("availableTagsContainer");
    tagsContainer.innerHTML = `<span class="text-[11px] text-slate-400 mr-1">Tags:</span>`;
    (data.headers || []).forEach(header => {
        const tag = document.createElement("span");
        tag.className = "cursor-pointer bg-slate-100 hover:bg-indigo-100 hover:text-indigo-700 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-mono transition";
        tag.textContent = `{{${header}}}`;
        tag.title = `Click to copy {{${header}}}`;
        tag.onclick = () => {
            navigator.clipboard.writeText(`{{${header}}}`);
            tag.classList.add("bg-indigo-200");
            setTimeout(() => tag.classList.remove("bg-indigo-200"), 500);
        };
        tagsContainer.appendChild(tag);
    });

    // Populate preview table
    const tableBody = document.getElementById("previewTableBody");
    tableBody.innerHTML = "";
    (data.preview || []).forEach((row, idx) => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50";
        const email = row.email || "-";
        const extra = row.name || row.company || (Object.keys(row).length > 1 ? JSON.stringify(row) : "-");
        tr.innerHTML = `
            <td class="px-3 py-1.5 text-slate-400 font-mono">${idx + 1}</td>
            <td class="px-3 py-1.5 font-medium text-slate-800">${escapeHtml(email)}</td>
            <td class="px-3 py-1.5 text-slate-500 truncate max-w-[150px]">${escapeHtml(extra)}</td>
        `;
        tableBody.appendChild(tr);
    });
}

function updateRecipientCountBadge(text, classNames) {
    const badge = document.getElementById("recipientsCountBadge");
    badge.textContent = text;
    badge.className = `text-xs font-semibold px-2.5 py-1 rounded-full border ${classNames}`;
}

// Attachment Handlers
async function fetchCurrentAttachments() {
    try {
        const res = await fetch("/api/get-attachments");
        const data = await res.json();
        if (data.success) {
            loadedAttachments = data.attachments || [];
            renderAttachmentsList();
        }
    } catch (e) {
        console.warn("Could not load initial attachments", e);
    }
}

async function handleAttachmentUpload(files) {
    if (!files || files.length === 0) return;
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append("attachments", files[i]);
    }

    try {
        const res = await fetch("/api/upload-attachments", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            loadedAttachments = data.attachments || [];
            renderAttachmentsList();
        } else {
            alert("Failed to upload attachment: " + (data.error || "Unknown error"));
        }
    } catch (err) {
        alert("Attachment upload failed: " + err.message);
    }
    // reset input
    document.getElementById("attachmentFileInput").value = "";
}

async function removeAttachment(id) {
    try {
        const res = await fetch("/api/remove-attachment", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.success) {
            loadedAttachments = data.attachments || [];
            renderAttachmentsList();
        }
    } catch (err) {
        console.error(err);
    }
}

function renderAttachmentsList() {
    const container = document.getElementById("attachmentsList");
    const countBadge = document.getElementById("attachmentCountBadge");
    const cardBadge = document.getElementById("cardAttachmentCount");

    container.innerHTML = "";
    const count = loadedAttachments.length;
    countBadge.textContent = `${count} ${count === 1 ? 'file' : 'files'} attached`;
    cardBadge.textContent = count;

    if (count === 0) {
        return;
    }

    loadedAttachments.forEach(att => {
        const card = document.createElement("div");
        card.className = "flex items-center justify-between p-2.5 bg-white rounded-lg border border-slate-200 text-xs shadow-xs hover:border-indigo-300 transition";
        card.innerHTML = `
            <div class="flex items-center space-x-2.5 overflow-hidden">
                <div class="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center text-sm flex-shrink-0">
                    <i class="fa-solid fa-file"></i>
                </div>
                <div class="overflow-hidden">
                    <p class="font-medium text-slate-800 truncate" title="${escapeHtml(att.name)}">${escapeHtml(att.name)}</p>
                    <p class="text-[11px] text-slate-400">${att.size_display || formatBytes(att.size_bytes)}</p>
                </div>
            </div>
            <button onclick="removeAttachment('${att.id}')" class="text-slate-400 hover:text-rose-500 p-1.5 transition ml-2" title="Remove attachment">
                <i class="fa-solid fa-xmark text-sm"></i>
            </button>
        `;
        container.appendChild(card);
    });
}

// SMTP Setup & Presets
function applyPreset(provider) {
    const hostInput = document.getElementById("smtpHost");
    const portInput = document.getElementById("smtpPort");
    const secSelect = document.getElementById("smtpSecurity");

    if (provider === "gmail") {
        hostInput.value = "smtp.gmail.com";
        portInput.value = "587";
        secSelect.value = "tls";
    } else if (provider === "office365") {
        hostInput.value = "smtp.office365.com";
        portInput.value = "587";
        secSelect.value = "tls";
    } else if (provider === "custom") {
        hostInput.value = "";
        portInput.value = "587";
        secSelect.value = "tls";
        hostInput.focus();
    }
}

function togglePasswordVisibility() {
    const pwdInput = document.getElementById("smtpPassword");
    const icon = document.getElementById("passwordToggleIcon");
    if (pwdInput.type === "password") {
        pwdInput.type = "text";
        icon.className = "fa-regular fa-eye-slash text-xs";
    } else {
        pwdInput.type = "password";
        icon.className = "fa-regular fa-eye text-xs";
    }
}

function getSmtpPayload() {
    return {
        host: document.getElementById("smtpHost").value.trim(),
        port: parseInt(document.getElementById("smtpPort").value) || 587,
        username: document.getElementById("smtpUsername").value.trim(),
        password: document.getElementById("smtpPassword").value.trim(),
        use_ssl: document.getElementById("smtpSecurity").value === "ssl",
        sender_name: document.getElementById("smtpSenderName").value.trim(),
        reply_to: document.getElementById("smtpReplyTo").value.trim()
    };
}

async function testSmtpConnection() {
    const payload = getSmtpPayload();
    const btn = document.getElementById("testSmtpBtn");
    const resDiv = document.getElementById("smtpTestResult");
    const headerBadge = document.getElementById("headerSmtpStatusBadge");

    if (!payload.username || !payload.password) {
        resDiv.className = "text-xs p-3 rounded-xl bg-amber-50 text-amber-800 border border-amber-200 block";
        resDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1.5"></i> Please enter Sender Email and Password / App Password.`;
        return;
    }

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Testing...</span>`;
    resDiv.classList.add("hidden");

    try {
        const res = await fetch("/api/test-smtp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        resDiv.classList.remove("hidden");
        if (data.success) {
            resDiv.className = "text-xs p-3 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 block";
            resDiv.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600 mr-1.5"></i> ${escapeHtml(data.message)}`;
            headerBadge.className = "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200";
            headerBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-500 mr-1.5"></span> SMTP Ready`;
        } else {
            resDiv.className = "text-xs p-3 rounded-xl bg-rose-50 text-rose-800 border border-rose-200 block";
            resDiv.innerHTML = `<i class="fa-solid fa-circle-xmark text-rose-600 mr-1.5"></i> ${escapeHtml(data.message)}`;
            headerBadge.className = "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200";
            headerBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500 mr-1.5"></span> SMTP Error`;
        }
    } catch (err) {
        resDiv.className = "text-xs p-3 rounded-xl bg-rose-50 text-rose-800 border border-rose-200 block";
        resDiv.innerHTML = `<i class="fa-solid fa-circle-xmark text-rose-600 mr-1.5"></i> Connection test failed: ${escapeHtml(err.message)}`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-plug"></i> <span>Test Connection</span>`;
    }
}

async function saveSmtpSettings() {
    const payload = getSmtpPayload();
    try {
        await fetch("/api/save-smtp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        alert("SMTP configuration preferences saved locally!");
    } catch (err) {
        alert("Failed to save: " + err.message);
    }
}

// Bulk Send Launcher & Flow
function confirmAndSendBulk() {
    if (loadedRecipients.length === 0) {
        alert("Please load or paste recipients first (Step 1).");
        return;
    }

    const subject = document.getElementById("emailSubject").value.trim();
    if (!subject) {
        alert("Please provide an email Subject Line (Step 2).");
        document.getElementById("emailSubject").focus();
        return;
    }

    const body = document.getElementById("emailBody").value.trim();
    if (!body) {
        alert("Please provide an Email Body message (Step 2).");
        document.getElementById("emailBody").focus();
        return;
    }

    const dryRun = document.getElementById("dryRunCheckbox").checked;
    const smtp = getSmtpPayload();

    if (!dryRun) {
        if (!smtp.username || !smtp.password) {
            alert("Please provide your Sender Email and Password / App Password in Step 3.");
            return;
        }
    }

    // Populate modal summary
    document.getElementById("modalRecipientCount").textContent = `${loadedRecipients.length} recipients`;
    const attSummary = loadedAttachments.length > 0 
        ? `${loadedAttachments.length} file(s) attached` 
        : "None (Text only)";
    document.getElementById("modalAttachmentSummary").textContent = attSummary;
    document.getElementById("modalSenderEmail").textContent = smtp.username || "(Dry run test)";
    
    const modeEl = document.getElementById("modalMode");
    if (dryRun) {
        modeEl.textContent = "Dry-Run Simulation";
        modeEl.className = "font-bold text-amber-600";
    } else {
        modeEl.textContent = "Live Send";
        modeEl.className = "font-bold text-emerald-600";
    }

    document.getElementById("confirmModal").classList.remove("hidden");
}

function closeConfirmModal() {
    document.getElementById("confirmModal").classList.add("hidden");
}

async function executeBulkSend() {
    closeConfirmModal();

    const payload = {
        recipients: loadedRecipients,
        subject: document.getElementById("emailSubject").value.trim(),
        body: document.getElementById("emailBody").value.trim(),
        is_html: document.getElementById("isHtmlCheckbox").checked,
        delay_seconds: parseFloat(document.getElementById("delayInterval").value) || 1.0,
        dry_run: document.getElementById("dryRunCheckbox").checked,
        smtp: getSmtpPayload()
    };

    setSendingUIState(true);
    resetProgressUI(loadedRecipients.length);
    appendLiveLog("SYSTEM", "Starting bulk sending task...", "text-indigo-400");

    try {
        const res = await fetch("/api/send-bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            appendLiveLog("SYSTEM", `Task [${data.task_id}] initiated with ${data.attachment_count} attachment(s).`, "text-emerald-400");
            startProgressListening();
        } else {
            alert("Could not start send: " + (data.error || "Unknown error"));
            setSendingUIState(false);
            appendLiveLog("SYSTEM", "Error: " + data.error, "text-rose-400");
        }
    } catch (err) {
        alert("Failed to start send: " + err.message);
        setSendingUIState(false);
    }
}

function startProgressListening() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource("/api/send-status-stream");

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateProgressUI(data);

            if (data.status === "completed" || data.status === "stopped" || data.status === "error") {
                eventSource.close();
                setSendingUIState(false);
                document.getElementById("exportReportBtn").removeAttribute("disabled");
                document.getElementById("exportReportBtn").classList.remove("text-slate-400");
                document.getElementById("exportReportBtn").classList.add("text-indigo-600");
            }
        } catch (e) {
            console.error("Error parsing progress stream:", e);
        }
    };

    eventSource.onerror = () => {
        // Fallback to polling if SSE breaks
        if (eventSource) eventSource.close();
        pollProgress();
    };
}

async function pollProgress() {
    if (!isSendingActive) return;
    try {
        const res = await fetch("/api/send-status");
        const data = await res.json();
        if (data.success && data.has_task) {
            updateProgressUI(data.progress);
            if (data.progress.status === "running" || data.progress.status === "queued") {
                setTimeout(pollProgress, 1000);
            } else {
                setSendingUIState(false);
                document.getElementById("exportReportBtn").removeAttribute("disabled");
                document.getElementById("exportReportBtn").classList.remove("text-slate-400");
                document.getElementById("exportReportBtn").classList.add("text-indigo-600");
            }
        }
    } catch (err) {
        console.error(err);
    }
}

function updateProgressUI(data) {
    if (!data) return;

    const percent = data.progress_percent || 0;
    document.getElementById("progressBarFill").style.width = `${percent}%`;
    document.getElementById("progressPercentLabel").textContent = `${percent}%`;
    document.getElementById("statSent").textContent = data.sent || 0;
    document.getElementById("statFailed").textContent = data.failed || 0;
    document.getElementById("statTotal").textContent = data.total || 0;

    const statusLabel = document.getElementById("progressStatusLabel");
    const indicator = document.getElementById("statusIndicatorDot");

    if (data.status === "running") {
        statusLabel.textContent = `Sending (${data.sent + data.failed} of ${data.total})...`;
        indicator.className = "w-2.5 h-2.5 rounded-full bg-indigo-500 animate-ping";
    } else if (data.status === "completed") {
        statusLabel.textContent = "Finished! All emails sent.";
        indicator.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    } else if (data.status === "stopped") {
        statusLabel.textContent = "Stopped by user.";
        indicator.className = "w-2.5 h-2.5 rounded-full bg-amber-500";
    } else if (data.status === "error") {
        statusLabel.textContent = "Stopped due to error.";
        indicator.className = "w-2.5 h-2.5 rounded-full bg-rose-500";
    }

    if (data.current_email) {
        document.getElementById("currentProcessingEmail").textContent = `Active: ${data.current_email}`;
    }

    // Render latest logs
    if (data.logs && data.logs.length > 0) {
        renderLogs(data.logs);
    }
}

function renderLogs(logs) {
    const logBox = document.getElementById("liveActivityLog");
    logBox.innerHTML = "";
    logs.forEach(item => {
        let colorClass = "text-slate-300";
        let icon = "•";
        if (item.status === "sent") {
            colorClass = "text-emerald-400";
            icon = "✓";
        } else if (item.status === "failed") {
            colorClass = "text-rose-400";
            icon = "✗";
        } else if (item.status === "warning") {
            colorClass = "text-amber-400";
            icon = "!";
        }

        const div = document.createElement("div");
        div.className = "flex items-start space-x-2 leading-relaxed";
        div.innerHTML = `
            <span class="text-slate-500">[${item.timestamp || ""}]</span>
            <span class="${colorClass} font-bold">${icon}</span>
            <span class="text-slate-200 font-semibold">${escapeHtml(item.email)}:</span>
            <span class="${colorClass}">${escapeHtml(item.message || "")}</span>
        `;
        logBox.appendChild(div);
    });
    logBox.scrollTop = logBox.scrollHeight;
}

function appendLiveLog(email, msg, colorClass = "text-slate-300") {
    const logBox = document.getElementById("liveActivityLog");
    const timeStr = new Date().toLocaleTimeString();
    const div = document.createElement("div");
    div.className = "flex items-start space-x-2 leading-relaxed";
    div.innerHTML = `
        <span class="text-slate-500">[${timeStr}]</span>
        <span class="text-indigo-400 font-bold">•</span>
        <span class="text-slate-200 font-semibold">${escapeHtml(email)}:</span>
        <span class="${colorClass}">${escapeHtml(msg)}</span>
    `;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
}

function setSendingUIState(sending) {
    isSendingActive = sending;
    const sendBtn = document.getElementById("sendBulkBtn");
    const stopBtn = document.getElementById("stopSendBtn");

    if (sending) {
        sendBtn.classList.add("hidden");
        stopBtn.classList.remove("hidden");
    } else {
        sendBtn.classList.remove("hidden");
        stopBtn.classList.add("hidden");
    }
}

function resetProgressUI(total) {
    document.getElementById("progressBarFill").style.width = "0%";
    document.getElementById("progressPercentLabel").textContent = "0%";
    document.getElementById("statSent").textContent = "0";
    document.getElementById("statFailed").textContent = "0";
    document.getElementById("statTotal").textContent = total;
    document.getElementById("liveActivityLog").innerHTML = "";
}

async function stopSending() {
    if (!confirm("Are you sure you want to stop the bulk sending in progress?")) return;
    try {
        await fetch("/api/stop-send", { method: "POST" });
        appendLiveLog("SYSTEM", "Stop requested. Waiting for worker to finish current email...", "text-amber-400");
    } catch (err) {
        alert("Stop request failed: " + err.message);
    }
}

function exportReport() {
    window.location.href = "/api/export-report";
}

async function checkActiveTaskStatus() {
    try {
        const res = await fetch("/api/send-status");
        const data = await res.json();
        if (data.success && data.has_task && data.progress) {
            updateProgressUI(data.progress);
            if (data.progress.status === "running") {
                setSendingUIState(true);
                startProgressListening();
            }
        }
    } catch (e) {
        // quiet
    }
}

// Helpers
function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
