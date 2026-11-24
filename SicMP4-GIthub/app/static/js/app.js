(() => {
    "use strict";

    // DOM Elements
    const ffmpegDot = document.getElementById("ffmpegDot");
    const ffmpegText = document.getElementById("ffmpegText");
    const lanCopyBtn = document.getElementById("lanCopyBtn");
    const lanUrlText = document.getElementById("lanUrlText");

    const openStudioPillBtn = document.getElementById("openStudioPillBtn");
    const openStudioPillText = document.getElementById("openStudioPillText");
    const studioModal = document.getElementById("studioModal");
    const closeStudioModalBtn = document.getElementById("closeStudioModalBtn");

    const openLibraryBtn = document.getElementById("openLibraryBtn");
    const libraryModal = document.getElementById("libraryModal");
    const closeLibraryModalBtn = document.getElementById("closeLibraryModalBtn");

    const openCookiesBtn = document.getElementById("openCookiesBtn");
    const cookiesStatusDot = document.getElementById("cookiesStatusDot");
    const cookiesModal = document.getElementById("cookiesModal");
    const closeCookiesModalBtn = document.getElementById("closeCookiesModalBtn");
    const cookiesModalStatus = document.getElementById("cookiesModalStatus");
    const cookiesFileInput = document.getElementById("cookiesFileInput");
    const cookiesTextarea = document.getElementById("cookiesTextarea");
    const saveCookiesBtn = document.getElementById("saveCookiesBtn");
    const clearCookiesBtn = document.getElementById("clearCookiesBtn");
    const errorCookiesBtn = document.getElementById("errorCookiesBtn");

    const startupCookieModal = document.getElementById("startupCookieModal");
    const startupCookieServerStatus = document.getElementById("startupCookieServerStatus");
    const startupCookieUploadBtn = document.getElementById("startupCookieUploadBtn");
    const cancelCookieNoticeBtn = document.getElementById("cancelCookieNoticeBtn");
    const acceptCookieNoticeBtn = document.getElementById("acceptCookieNoticeBtn");

    const analyzeForm = document.getElementById("analyzeForm");
    const urlInput = document.getElementById("urlInput");
    const clearUrlBtn = document.getElementById("clearUrlBtn");
    const pasteBtn = document.getElementById("pasteBtn");
    const analyzeBtn = document.getElementById("analyzeBtn");
    const analyzeSpinner = document.getElementById("analyzeSpinner");
    const analyzePlayIcon = document.getElementById("analyzePlayIcon");
    const analyzeBtnText = document.getElementById("analyzeBtnText");

    const errorAlert = document.getElementById("errorAlert");
    const errorAlertText = document.getElementById("errorAlertText");
    const skeletonCard = document.getElementById("skeletonCard");
    const mediaCard = document.getElementById("mediaCard");

    const mediaThumb = document.getElementById("mediaThumb");
    const mediaExtractor = document.getElementById("mediaExtractor");
    const mediaDuration = document.getElementById("mediaDuration");
    const mediaTitle = document.getElementById("mediaTitle");
    const mediaAuthor = document.getElementById("mediaAuthor");
    const mediaMaxResBadge = document.getElementById("mediaMaxResBadge");
    const mediaSubsBadge = document.getElementById("mediaSubsBadge");

    const formatTabs = document.querySelectorAll(".format-tab");
    const qualitySectionLabel = document.getElementById("qualitySectionLabel");
    const qualityGrid = document.getElementById("qualityGrid");

    const toggleExtraBtn = document.getElementById("toggleExtraBtn");
    const toggleExtraChevron = document.getElementById("toggleExtraChevron");
    const extraOptionsPanel = document.getElementById("extraOptionsPanel");
    const clipStartInput = document.getElementById("clipStartInput");
    const clipEndInput = document.getElementById("clipEndInput");
    const subtitleModeSelect = document.getElementById("subtitleModeSelect");
    const playlistCheckbox = document.getElementById("playlistCheckbox");

    const selectionSummary = document.getElementById("selectionSummary");
    const startDownloadBtn = document.getElementById("startDownloadBtn");

    const tasksSection = document.getElementById("tasksSection");
    const tasksList = document.getElementById("tasksList");

    const filesCountBadge = document.getElementById("filesCountBadge");
    const refreshFilesBtn = document.getElementById("refreshFilesBtn");
    const openFolderMainBtn = document.getElementById("openFolderMainBtn");
    const savedFilesEmpty = document.getElementById("savedFilesEmpty");
    const savedFilesList = document.getElementById("savedFilesList");
    const toastEl = document.getElementById("toast");

    // Application State
    let currentMedia = null;
    let selectedCategory = "mp4";
    let selectedVariantKey = "mp4:1080";
    let lanUrl = "";
    let lastAnalyzedUrl = "";
    let activeInfoController = null;
    let hasActiveSession = false;
    let isDesktopApp = false;
    let serverNativeHostUi = false;

    const isLocalHostClient = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    const isPrivateLanOrLocal =
        isLocalHostClient ||
        /^192\.168\.\d+\.\d+$/.test(window.location.hostname) ||
        /^10\.\d+\.\d+\.\d+$/.test(window.location.hostname);
    const canUseNativeHost = () => isLocalHostClient && serverNativeHostUi;

    const autoTriggeredTasks = new Set();
    const completedTasksNotified = new Set();
    const pendingTaskFrames = new Map();
    const latestTaskStates = new Map();

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str == null ? "" : String(str);
        return div.innerHTML;
    }

    let toastTimer = null;
    function showToast(message) {
        toastEl.textContent = message;
        toastEl.classList.remove("hidden");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toastEl.classList.add("hidden");
        }, 2800);
    }

    function showError(msg) {
        if (!msg) {
            errorAlert.classList.add("hidden");
            errorAlertText.textContent = "";
            if (errorCookiesBtn) errorCookiesBtn.classList.add("hidden");
            return;
        }
        const isBotAuthErr = /not a bot|cookies|sign in to confirm/i.test(msg);
        if (isBotAuthErr) {
            errorAlertText.textContent =
                "YouTube wymaga autoryzacji sesji (cookies.txt) na adresach IP serwerów chmurowych (np. Render). Dodaj swoje cookies.txt, aby odblokować pobieranie.";
            if (errorCookiesBtn) errorCookiesBtn.classList.remove("hidden");
        } else {
            errorAlertText.textContent = msg;
            if (errorCookiesBtn) errorCookiesBtn.classList.add("hidden");
        }
        errorAlert.classList.remove("hidden");
    }

    function syncClearBtn() {
        if (urlInput.value.trim().length > 0) {
            clearUrlBtn.classList.remove("hidden");
        } else {
            clearUrlBtn.classList.add("hidden");
        }
    }

    // Modal helpers
    function openStudioModal() {
        libraryModal.classList.add("hidden");
        if (cookiesModal) cookiesModal.classList.add("hidden");
        studioModal.classList.remove("hidden");
    }

    function closeStudioModal() {
        studioModal.classList.add("hidden");
        if (hasActiveSession) {
            openStudioPillBtn.classList.remove("hidden");
            openStudioPillBtn.classList.add("flex");
        }
    }

    function openLibraryModal() {
        studioModal.classList.add("hidden");
        if (cookiesModal) cookiesModal.classList.add("hidden");
        loadSavedFiles();
        libraryModal.classList.remove("hidden");
    }

    function closeLibraryModal() {
        libraryModal.classList.add("hidden");
    }

    function openCookiesModal() {
        studioModal.classList.add("hidden");
        libraryModal.classList.add("hidden");
        if (cookiesModal) cookiesModal.classList.remove("hidden");
    }

    function closeCookiesModal() {
        if (cookiesModal) cookiesModal.classList.add("hidden");
    }

    function updateCookiesBadge(cookiesInfo) {
        if (cookiesStatusDot) {
            if (cookiesInfo && cookiesInfo.configured) {
                cookiesStatusDot.className = "w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]";
                if (cookiesModalStatus) {
                    cookiesModalStatus.textContent = `Status: Aktywne cookies (${cookiesInfo.source})`;
                }
            } else {
                cookiesStatusDot.className = "w-2 h-2 rounded-full bg-neutral-500";
                if (cookiesModalStatus) {
                    cookiesModalStatus.textContent = "Status: Brak wgranych cookies (zalecane dla YouTube na Render / VPS)";
                }
            }
        }

        if (startupCookieServerStatus) {
            if (cookiesInfo && cookiesInfo.configured) {
                startupCookieServerStatus.innerHTML = `<span class="text-emerald-400 font-semibold">Status serwera: Aktywne cookies (${escapeHtml(cookiesInfo.source)}). Pobieranie z YouTube jest w pełni odblokowane dla wszystkich.</span>`;
            } else {
                startupCookieServerStatus.innerHTML = `<span class="text-amber-400 font-medium">Status serwera: Brak aktywnych cookies. Na publicznym hostingu YouTube może wymagać autoryzacji cookies.txt.</span>`;
            }
        }
    }

    function openStartupCookieModal() {
        if (startupCookieModal) startupCookieModal.classList.remove("hidden");
    }

    function closeStartupCookieModal() {
        if (startupCookieModal) startupCookieModal.classList.add("hidden");
    }

    function initStartupCookieNotice() {
        const decision = sessionStorage.getItem("sicmp4_cookie_decision") || localStorage.getItem("sicmp4_cookie_decision");
        if (!decision) {
            openStartupCookieModal();
        }
    }

    closeStudioModalBtn.addEventListener("click", closeStudioModal);
    openStudioPillBtn.addEventListener("click", openStudioModal);
    openLibraryBtn.addEventListener("click", openLibraryModal);
    closeLibraryModalBtn.addEventListener("click", closeLibraryModal);
    if (openCookiesBtn) openCookiesBtn.addEventListener("click", openCookiesModal);
    if (closeCookiesModalBtn) closeCookiesModalBtn.addEventListener("click", closeCookiesModal);
    if (errorCookiesBtn) errorCookiesBtn.addEventListener("click", openCookiesModal);

    if (cookiesModal) {
        cookiesModal.addEventListener("click", (e) => {
            if (e.target === cookiesModal) closeCookiesModal();
        });
    }

    if (cookiesFileInput) {
        cookiesFileInput.addEventListener("change", async (e) => {
            const file = e.target.files && e.target.files[0];
            if (!file) return;
            const text = await file.text();
            cookiesTextarea.value = text;
            showToast(`Wczytano plik: ${file.name}`);
        });
    }

    if (saveCookiesBtn) {
        saveCookiesBtn.addEventListener("click", async () => {
            const raw = cookiesTextarea.value.trim();
            if (!raw) {
                showToast("Wklej zawartość lub wybierz plik cookies.txt");
                return;
            }
            saveCookiesBtn.disabled = true;
            try {
                const res = await fetch("/api/cookies", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cookies_text: raw }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Nieprawidłowy format cookies.txt");
                updateCookiesBadge(data);
                cookiesTextarea.value = "";
                closeCookiesModal();
                showError("");
                showToast(`Aktywowano cookies (${data.entries || "OK"} wpisów)`);
                const currentUrl = urlInput.value.trim();
                if (/^https?:\/\/\S+/i.test(currentUrl)) {
                    lastAnalyzedUrl = "";
                    analyzeUrl(currentUrl);
                }
            } catch (err) {
                showToast(err.message || "Błąd zapisu cookies.txt");
            } finally {
                saveCookiesBtn.disabled = false;
            }
        });
    }

    if (clearCookiesBtn) {
        clearCookiesBtn.addEventListener("click", async () => {
            const res = await fetch("/api/cookies", { method: "DELETE" });
            if (res.ok) {
                const data = await res.json();
                updateCookiesBadge(data);
                cookiesTextarea.value = "";
                showToast("Usunięto zapisane cookies z panelu");
            }
        });
    }

    if (acceptCookieNoticeBtn) {
        acceptCookieNoticeBtn.addEventListener("click", () => {
            sessionStorage.setItem("sicmp4_cookie_decision", "accepted");
            localStorage.setItem("sicmp4_cookie_decision", "accepted");
            closeStartupCookieModal();
            showToast("Zaakceptowano informację o plikach cookies");
        });
    }

    if (cancelCookieNoticeBtn) {
        cancelCookieNoticeBtn.addEventListener("click", () => {
            sessionStorage.setItem("sicmp4_cookie_decision", "dismissed");
            localStorage.setItem("sicmp4_cookie_decision", "dismissed");
            closeStartupCookieModal();
            showToast("Kontynuujesz bez cookies (inne serwisy działają normalnie)");
        });
    }

    if (startupCookieUploadBtn) {
        startupCookieUploadBtn.addEventListener("click", () => {
            closeStartupCookieModal();
            openCookiesModal();
        });
    }

    if (startupCookieModal) {
        startupCookieModal.addEventListener("click", (e) => {
            if (e.target === startupCookieModal) {
                closeStartupCookieModal();
            }
        });
    }

    studioModal.addEventListener("click", (e) => {
        if (e.target === studioModal) closeStudioModal();
    });

    libraryModal.addEventListener("click", (e) => {
        if (e.target === libraryModal) closeLibraryModal();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            if (!studioModal.classList.contains("hidden")) closeStudioModal();
            if (!libraryModal.classList.contains("hidden")) closeLibraryModal();
            if (cookiesModal && !cookiesModal.classList.contains("hidden")) closeCookiesModal();
            if (startupCookieModal && !startupCookieModal.classList.contains("hidden")) closeStartupCookieModal();
        }
    });

    toggleExtraBtn.addEventListener("click", () => {
        const isHidden = extraOptionsPanel.classList.toggle("hidden");
        toggleExtraChevron.style.transform = isHidden ? "rotate(0deg)" : "rotate(180deg)";
    });

    // 1. Health check, Adaptive Mode Detection & LAN address
    async function checkHealth() {
        try {
            const res = await fetch("/api/health");
            if (!res.ok) throw new Error("Health check failed");
            const data = await res.json();

            isDesktopApp = Boolean(data.desktop);
            serverNativeHostUi = Boolean(data.native_host_ui);

            if (openCookiesBtn) {
                if (isDesktopApp) {
                    openCookiesBtn.classList.add("hidden");
                    openCookiesBtn.classList.remove("flex");
                } else {
                    openCookiesBtn.classList.remove("hidden");
                    openCookiesBtn.classList.add("flex");
                }
            }

            openFolderMainBtn.classList.toggle("hidden", !canUseNativeHost());

            if (data.ffmpeg && data.ffmpeg.available) {
                ffmpegDot.className = "w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.85)]";
                ffmpegText.textContent = `FFmpeg gotowy • yt-dlp ${data.ffmpeg.yt_dlp_version || ""}`;
            } else {
                ffmpegDot.className = "w-2 h-2 rounded-full bg-red-500";
                ffmpegText.textContent = "Brak FFmpeg!";
            }

            if (data.cookies) {
                updateCookiesBadge(data.cookies);
            }

            if (!isDesktopApp && isPrivateLanOrLocal && data.lan_url && !data.lan_url.includes("127.0.0.1")) {
                lanUrl = data.lan_url;
                lanUrlText.textContent = data.lan_url.replace("http://", "");
                lanCopyBtn.classList.remove("hidden");
                lanCopyBtn.classList.add("flex");
            } else {
                lanUrl = "";
                lanCopyBtn.classList.add("hidden");
                lanCopyBtn.classList.remove("sm:flex", "flex");
            }

            if (!isDesktopApp && !isPrivateLanOrLocal && !(data.cookies && data.cookies.configured)) {
                initStartupCookieNotice();
            }
        } catch {
            ffmpegDot.className = "w-2 h-2 rounded-full bg-red-500";
            ffmpegText.textContent = "Brak połączenia z API";
        }
    }

    lanCopyBtn.addEventListener("click", async () => {
        if (!lanUrl) return;
        try {
            await navigator.clipboard.writeText(lanUrl);
            showToast(`Skopiowano adres LAN: ${lanUrl}`);
        } catch {
            showToast(`Adres w sieci LAN: ${lanUrl}`);
        }
    });

    // 2. Input & Paste handling
    urlInput.addEventListener("input", syncClearBtn);

    clearUrlBtn.addEventListener("click", () => {
        urlInput.value = "";
        lastAnalyzedUrl = "";
        syncClearBtn();
        showError("");
        urlInput.focus();
    });

    pasteBtn.addEventListener("click", async () => {
        let clip = "";
        if (canUseNativeHost()) {
            try {
                const res = await fetch("/api/clipboard");
                if (res.ok) {
                    const data = await res.json();
                    clip = (data && data.text) || "";
                }
            } catch {
                clip = "";
            }
        }
        if (!clip) {
            try {
                clip = await navigator.clipboard.readText();
            } catch {
                clip = "";
            }
        }
        if (clip && clip.trim()) {
            urlInput.value = clip.trim();
            syncClearBtn();
            if (/^https?:\/\/\S+/i.test(urlInput.value)) {
                analyzeUrl(urlInput.value);
            }
        } else {
            urlInput.focus();
            showToast("Schowek jest pusty lub użyj skrótu Ctrl+V");
        }
    });

    urlInput.addEventListener("paste", () => {
        setTimeout(() => {
            syncClearBtn();
            const val = urlInput.value.trim();
            if (/^https?:\/\/\S+/i.test(val) && val !== lastAnalyzedUrl) {
                analyzeUrl(val);
            }
        }, 60);
    });

    analyzeForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const val = urlInput.value.trim();
        if (val) {
            analyzeUrl(val);
        }
    });

    // 3. Metadata Fetching (with AbortController cancellation for rapid pastes)
    async function analyzeUrl(rawUrl) {
        if (activeInfoController) {
            activeInfoController.abort();
        }
        const controller = new AbortController();
        activeInfoController = controller;
        lastAnalyzedUrl = rawUrl;
        showError("");

        analyzeBtn.disabled = true;
        analyzeSpinner.classList.remove("hidden");
        if (analyzePlayIcon) analyzePlayIcon.classList.add("hidden");
        analyzeBtnText.textContent = "Analizuję...";

        mediaCard.classList.add("hidden");
        skeletonCard.classList.remove("hidden");
        openStudioModal();

        try {
            const res = await fetch("/api/info", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: rawUrl }),
                signal: controller.signal,
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Nie udało się pobrać informacji o materiale.");
            }

            currentMedia = data;
            hasActiveSession = true;
            renderMediaPreview(data);
        } catch (err) {
            if (err && err.name === "AbortError") {
                return;
            }
            if (!hasActiveSession) {
                studioModal.classList.add("hidden");
            }
            showError(err.message || "Wystąpił błąd podczas analizy linku.");
            lastAnalyzedUrl = "";
        } finally {
            if (activeInfoController === controller) {
                activeInfoController = null;
                analyzeBtn.disabled = false;
                analyzeSpinner.classList.add("hidden");
                if (analyzePlayIcon) analyzePlayIcon.classList.remove("hidden");
                analyzeBtnText.textContent = "Sprawdź link";
                skeletonCard.classList.add("hidden");
            }
        }
    }

    function renderMediaPreview(data) {
        mediaTitle.textContent = data.title || "Bez tytułu";
        mediaAuthor.textContent = data.author || "Nieznany autor";
        mediaDuration.textContent = data.duration_string || "—";
        mediaExtractor.textContent = data.extractor || "Web";

        if (data.thumbnail) {
            mediaThumb.src = data.thumbnail;
        } else {
            mediaThumb.src =
                "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'%3E%3Crect width='640' height='360' fill='%230c0806'/%3E%3Ctext x='50%25' y='50%25' fill='%23a8a29e' font-family='sans-serif' font-size='20' text-anchor='middle'%3ESicMP4%3C/text%3E%3C/svg%3E";
        }

        const heights = data.available_heights || [];
        if (data.is_playlist) {
            mediaMaxResBadge.textContent = `Playlista (${data.playlist_count || "wiele"} poz.)`;
            playlistCheckbox.checked = true;
            extraOptionsPanel.classList.remove("hidden");
            toggleExtraChevron.style.transform = "rotate(180deg)";
        } else if (heights.length > 0) {
            const maxH = heights[0];
            const tag = maxH >= 2160 ? `4K (${maxH}p)` : maxH >= 1440 ? `2K (${maxH}p)` : `${maxH}p`;
            mediaMaxResBadge.textContent = `Maks. jakość: ${tag}`;
            playlistCheckbox.checked = false;
        } else {
            mediaMaxResBadge.textContent = "Strumień audio / wideo";
            playlistCheckbox.checked = false;
        }

        if (data.has_subtitles && Array.isArray(data.subtitle_langs) && data.subtitle_langs.length > 0) {
            mediaSubsBadge.textContent = `Napisy (${data.subtitle_langs.slice(0, 4).join(", ")})`;
            mediaSubsBadge.classList.remove("hidden");
        } else {
            mediaSubsBadge.classList.add("hidden");
        }

        pickDefaultVariantForCategory(selectedCategory);
        renderQualityOptions();
        mediaCard.classList.remove("hidden");
    }

    // 4. Format Categories & Quality Variants (delegated click handler)
    function pickDefaultVariantForCategory(cat) {
        const heights = (currentMedia && currentMedia.available_heights) || [];
        if (cat === "mp4") {
            selectedVariantKey = heights.includes(1080) ? "mp4:1080" : "mp4:best";
        } else if (cat === "audio") {
            selectedVariantKey = "mp3:320";
        } else {
            selectedVariantKey = "mkv:best";
            if (subtitleModeSelect.value === "none") {
                subtitleModeSelect.value = "embed";
            }
        }
    }

    formatTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const cat = tab.dataset.format;
            if (!cat) return;
            selectedCategory = cat;

            formatTabs.forEach((t) => t.classList.remove("format-tab-active"));
            tab.classList.add("format-tab-active");

            pickDefaultVariantForCategory(cat);
            renderQualityOptions();
        });
    });

    qualityGrid.addEventListener("click", (e) => {
        const btn = e.target.closest(".quality-tile");
        if (!btn || !qualityGrid.contains(btn)) return;
        selectedVariantKey = btn.dataset.variantKey;
        renderQualityOptions();
    });

    function getSizeHintForHeight(height) {
        if (!currentMedia || !Array.isArray(currentMedia.resolutions)) return null;
        const found = currentMedia.resolutions.find((r) => r.height === height);
        return found ? found.filesize_str : null;
    }

    function buildQualityItems() {
        const heights = (currentMedia && currentMedia.available_heights) || [];
        const maxH = heights.length > 0 ? heights[0] : null;

        if (selectedCategory === "mp4") {
            qualitySectionLabel.textContent = "2. Wybierz rozdzielczość wideo MP4 (H.264 / AAC)";
            subtitleModeSelect.disabled = false;

            const items = [
                {
                    key: "mp4:best",
                    format_type: "mp4",
                    quality: "best",
                    title: "Najlepsza dostępna",
                    sub: maxH ? `Maks. źródło (${maxH}p)` : "Automatyczna MAX",
                    available: true,
                },
            ];

            if (heights.includes(2160)) {
                items.push({
                    key: "mp4:2160",
                    format_type: "mp4",
                    quality: "2160",
                    title: "2160p (4K Ultra HD)",
                    sub: getSizeHintForHeight(2160) ? `~${getSizeHintForHeight(2160)}` : "Ultra HD",
                    available: true,
                });
            }
            if (heights.includes(1440)) {
                items.push({
                    key: "mp4:1440",
                    format_type: "mp4",
                    quality: "1440",
                    title: "1440p (2K Quad HD)",
                    sub: getSizeHintForHeight(1440) ? `~${getSizeHintForHeight(1440)}` : "Quad HD",
                    available: true,
                });
            }

            [
                { h: 1080, name: "1080p Full HD" },
                { h: 720, name: "720p HD" },
                { h: 480, name: "480p SD" },
            ].forEach(({ h, name }) => {
                const exactOrHigher = !maxH || maxH >= h || heights.includes(h);
                const sizeHint = getSizeHintForHeight(h);
                items.push({
                    key: `mp4:${h}`,
                    format_type: "mp4",
                    quality: String(h),
                    title: name,
                    sub: sizeHint
                        ? `~${sizeHint}`
                        : exactOrHigher
                        ? "Dostępna"
                        : `Skalowana do maks. ${maxH}p`,
                    available: exactOrHigher,
                });
            });

            return items;
        }

        if (selectedCategory === "audio") {
            qualitySectionLabel.textContent = "2. Wybierz format i jakość dźwięku";
            subtitleModeSelect.disabled = true;
            return [
                {
                    key: "mp3:320",
                    format_type: "mp3",
                    quality: "320",
                    title: "MP3 • 320 kbps",
                    sub: "Studyjna + ID3 + Okładka",
                    available: true,
                },
                {
                    key: "mp3:192",
                    format_type: "mp3",
                    quality: "192",
                    title: "MP3 • 192 kbps",
                    sub: "Wysoka jakość + ID3 + Okładka",
                    available: true,
                },
                {
                    key: "m4a:best",
                    format_type: "m4a",
                    quality: "best",
                    title: "M4A / AAC",
                    sub: "Natywny strumień audio",
                    available: true,
                },
                {
                    key: "flac:best",
                    format_type: "flac",
                    quality: "best",
                    title: "FLAC (Bezstratny)",
                    sub: "Archival Lossless Audio",
                    available: true,
                },
                {
                    key: "wav:best",
                    format_type: "wav",
                    quality: "best",
                    title: "WAV (PCM)",
                    sub: "Nieskompresowany dźwięk",
                    available: true,
                },
            ];
        }

        qualitySectionLabel.textContent = "2. Wybierz kontener bezstratny (MKV / WebM)";
        subtitleModeSelect.disabled = false;
        return [
            {
                key: "mkv:best",
                format_type: "mkv",
                quality: "best",
                title: "MKV • MAX Bezstratny",
                sub: maxH ? `Oryginalne kodeki (${maxH}p)` : "Oryginalne strumienie",
                available: true,
            },
            {
                key: "mkv:1080",
                format_type: "mkv",
                quality: "1080",
                title: "MKV • Do 1080p",
                sub: getSizeHintForHeight(1080) ? `~${getSizeHintForHeight(1080)}` : "Bezstratny remux",
                available: true,
            },
            {
                key: "mkv:720",
                format_type: "mkv",
                quality: "720",
                title: "MKV • Do 720p",
                sub: getSizeHintForHeight(720) ? `~${getSizeHintForHeight(720)}` : "Bezstratny remux",
                available: true,
            },
            {
                key: "webm:best",
                format_type: "webm",
                quality: "best",
                title: "WebM (VP9 / AV1)",
                sub: "Natywne strumienie WebM",
                available: true,
            },
        ];
    }

    function renderQualityOptions() {
        const items = buildQualityItems();
        if (!items.some((i) => i.key === selectedVariantKey)) {
            selectedVariantKey = items[0].key;
        }

        qualityGrid.innerHTML = items
            .map((item) => {
                const isActive = item.key === selectedVariantKey;
                return `
                    <button type="button" data-variant-key="${escapeHtml(item.key)}"
                        class="quality-tile ${isActive ? "quality-tile-active" : ""} text-left p-3 rounded-xl border border-white/10 bg-white/[0.03] hover:border-amber-400/50 transition cursor-pointer">
                        <div class="flex items-center justify-between gap-1">
                            <span class="font-semibold text-xs sm:text-sm text-white">${escapeHtml(item.title)}</span>
                            ${
                                isActive
                                    ? `<span class="w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.9)] shrink-0"></span>`
                                    : ""
                            }
                        </div>
                        <div class="mt-1 text-[11px] ${item.available ? "text-neutral-400" : "text-amber-400/85"} font-mono-num truncate">
                            ${escapeHtml(item.sub)}
                        </div>
                    </button>
                `;
            })
            .join("");

        updateSummaryText(items);
    }

    function getActiveVariant() {
        const items = buildQualityItems();
        return items.find((i) => i.key === selectedVariantKey) || items[0];
    }

    function updateSummaryText(items) {
        const chosen = items.find((i) => i.key === selectedVariantKey) || items[0];
        const parts = [];

        const cs = clipStartInput.value.trim();
        const ce = clipEndInput.value.trim();
        if (cs || ce) {
            parts.push(`Wycinek ${cs || "00:00"}–${ce || "koniec"}`);
        }

        if (selectedCategory !== "audio" && subtitleModeSelect.value !== "none") {
            const subLabels = {
                embed: "Napisy osadzone",
                srt: "Plik .srt",
                burn: "Wtopione napisy",
            };
            parts.push(subLabels[subtitleModeSelect.value] || "");
        }

        if (playlistCheckbox.checked) {
            parts.push("Cała playlista");
        }

        const extraText = parts.length > 0 ? ` • ${parts.join(" • ")}` : "";
        selectionSummary.innerHTML = `Wybrano: <strong class="text-amber-300">${escapeHtml(chosen.format_type.toUpperCase())} • ${escapeHtml(chosen.title)}</strong><span class="text-neutral-400">${escapeHtml(extraText)}</span>`;
    }

    [clipStartInput, clipEndInput, subtitleModeSelect, playlistCheckbox].forEach((el) => {
        el.addEventListener("input", () => updateSummaryText(buildQualityItems()));
        el.addEventListener("change", () => updateSummaryText(buildQualityItems()));
    });

    // 5. Starting Downloads & Real-Time SSE Progress (rAF-coalesced)
    startDownloadBtn.addEventListener("click", async () => {
        const targetUrl = (currentMedia && currentMedia.url) || urlInput.value.trim();
        if (!targetUrl) {
            showError("Najpierw wklej link do filmu lub utworu.");
            return;
        }

        const chosen = getActiveVariant();
        startDownloadBtn.disabled = true;
        try {
            const res = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: targetUrl,
                    format_type: chosen.format_type,
                    quality: chosen.quality,
                    title: currentMedia ? currentMedia.title : "",
                    thumbnail: currentMedia ? currentMedia.thumbnail : "",
                    subtitle_mode: selectedCategory === "audio" ? "none" : subtitleModeSelect.value,
                    clip_start: clipStartInput.value.trim(),
                    clip_end: clipEndInput.value.trim(),
                    allow_playlist: playlistCheckbox.checked,
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Nie udało się uruchomić pobierania.");
            }

            hasActiveSession = true;
            createTaskCard(data.state);
            subscribeToTaskProgress(data.task_id);
            showToast("Rozpoczęto pobieranie!");
        } catch (err) {
            showError(err.message || "Błąd podczas uruchamiania pobierania.");
        } finally {
            startDownloadBtn.disabled = false;
        }
    });

    function formatBadgeLabel(formatType, quality) {
        const fmt = (formatType || "mp4").toUpperCase();
        if (fmt === "MP3") return `MP3 • ${quality} kbps`;
        if (["M4A", "FLAC", "WAV"].includes(fmt)) return fmt;
        if (quality === "best") return `${fmt} • MAX`;
        return `${fmt} • ${quality}p`;
    }

    function createTaskCard(state) {
        tasksSection.classList.remove("hidden");
        const card = document.createElement("div");
        card.id = `task-${state.task_id}`;
        card.className = "rounded-2xl p-4 bg-white/[0.03] border border-white/10 space-y-3 transition-all";

        const nativeHost = canUseNativeHost();
        const badge = formatBadgeLabel(state.format_type, state.quality);
        card.innerHTML = `
            <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3 min-w-0">
                    ${
                        state.thumbnail
                            ? `<img src="${escapeHtml(state.thumbnail)}" alt="" class="w-16 h-10 object-cover rounded-lg border border-white/15 shrink-0 hidden sm:block" />`
                            : ""
                    }
                    <div class="min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-[10px] font-mono-num font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/35">
                                ${escapeHtml(badge)}
                            </span>
                            <span data-role="stage" class="text-xs text-neutral-400 truncate">
                                ${escapeHtml(state.stage || "Inicjalizacja...")}
                            </span>
                        </div>
                        <h4 data-role="title" class="text-sm font-semibold text-white truncate mt-1">
                            ${escapeHtml(state.title || "Pobieranie...")}
                        </h4>
                    </div>
                </div>
                <span data-role="percent" class="text-sm font-mono-num font-bold text-amber-300 shrink-0">
                    0.0%
                </span>
            </div>

            <div class="w-full h-2.5 bg-black rounded-full overflow-hidden border border-white/15">
                <div data-role="bar" class="h-full progress-shimmer rounded-full transition-all duration-300 ease-out" style="width: 1%"></div>
            </div>

            <div data-role="telemetry" class="flex flex-wrap items-center justify-between gap-2 text-xs font-mono-num text-neutral-400">
                <span>Pobrano: <strong data-role="downloaded" class="text-white">0 B</strong></span>
                <div class="flex items-center gap-4">
                    <span>Prędkość: <strong data-role="speed" class="text-amber-300">—</strong></span>
                    <span>ETA: <strong data-role="eta" class="text-white">—</strong></span>
                </div>
            </div>

            <div data-role="error" class="hidden p-3 rounded-xl bg-red-950/65 border border-red-500/35 text-xs text-red-200 break-words"></div>

            <div data-role="actions" class="hidden pt-2 flex flex-wrap items-center justify-between gap-3 border-t border-white/10">
                <span data-role="fileinfo" class="text-xs font-mono-num text-amber-300 truncate max-w-full sm:max-w-[50%]"></span>
                <div class="flex flex-wrap items-center gap-2 ml-auto">
                    ${
                        nativeHost
                            ? `<button type="button" data-role="open-folder-btn"
                                class="px-4 py-2 rounded-full bg-white/10 hover:bg-white hover:text-black text-xs font-bold text-white border border-white/20 transition flex items-center gap-1.5 cursor-pointer">
                                <svg class="w-3.5 h-3.5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                                </svg>
                                <span>Pokaż w folderze</span>
                               </button>`
                            : ""
                    }
                    <a data-role="download-link" href="/api/file/${encodeURIComponent(state.task_id)}" download
                        class="px-5 py-2 rounded-full bg-amber-300 hover:bg-white text-xs font-extrabold text-black transition flex items-center gap-1.5 cursor-pointer">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.3">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" />
                        </svg>
                        <span>${nativeHost ? "Zapisz jako..." : "Pobierz na dysk"}</span>
                    </a>
                </div>
            </div>
        `;

        const openBtn = card.querySelector('[data-role="open-folder-btn"]');
        if (openBtn) {
            openBtn.addEventListener("click", () => openDownloadsFolder({ task_id: state.task_id }));
        }

        const dlLink = card.querySelector('[data-role="download-link"]');
        if (dlLink && nativeHost) {
            dlLink.addEventListener("click", (e) => {
                e.preventDefault();
                saveFileAsDialog({ task_id: state.task_id });
            });
        }

        tasksList.prepend(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function scheduleTaskCardUI(state) {
        if (!state || !state.task_id) return;
        latestTaskStates.set(state.task_id, state);
        if (pendingTaskFrames.has(state.task_id)) return;
        const rafId = requestAnimationFrame(() => {
            pendingTaskFrames.delete(state.task_id);
            const latest = latestTaskStates.get(state.task_id);
            if (latest) {
                updateTaskCardUI(latest);
            }
        });
        pendingTaskFrames.set(state.task_id, rafId);
    }

    function updateTaskCardUI(state) {
        const card = document.getElementById(`task-${state.task_id}`);
        if (!card) return;

        const titleEl = card.querySelector('[data-role="title"]');
        const stageEl = card.querySelector('[data-role="stage"]');
        const pctEl = card.querySelector('[data-role="percent"]');
        const barEl = card.querySelector('[data-role="bar"]');
        const dlEl = card.querySelector('[data-role="downloaded"]');
        const speedEl = card.querySelector('[data-role="speed"]');
        const etaEl = card.querySelector('[data-role="eta"]');
        const telemetryEl = card.querySelector('[data-role="telemetry"]');
        const errorEl = card.querySelector('[data-role="error"]');
        const actionsEl = card.querySelector('[data-role="actions"]');
        const fileInfoEl = card.querySelector('[data-role="fileinfo"]');

        if (state.title) titleEl.textContent = state.title;
        if (state.stage) stageEl.textContent = state.stage;

        const pct = typeof state.percent === "number" ? Math.min(100, Math.max(0, state.percent)) : 0;
        pctEl.textContent = `${pct.toFixed(1)}%`;
        barEl.style.width = `${Math.max(1, pct)}%`;

        if (state.downloaded_str) dlEl.textContent = state.downloaded_str;
        if (state.speed) speedEl.textContent = state.speed;
        if (state.eta) etaEl.textContent = state.eta;

        if (state.status === "downloading" || state.status === "processing") {
            openStudioPillText.textContent = `Pobieranie: ${pct.toFixed(0)}%`;
        } else if (state.status === "completed") {
            openStudioPillText.textContent = "Gotowe do pobrania";
            barEl.classList.remove("progress-shimmer");
            barEl.classList.add("bg-gradient-to-r", "from-amber-400", "to-orange-500");
            pctEl.className = "text-sm font-mono-num font-bold text-amber-300 shrink-0";
            stageEl.className = "text-xs text-amber-300 font-medium truncate";
            telemetryEl.classList.add("hidden");
            actionsEl.classList.remove("hidden");
            fileInfoEl.textContent = `${state.filename || "Plik gotowy"} (${state.filesize_str || ""})`;

            if (!completedTasksNotified.has(state.task_id)) {
                completedTasksNotified.add(state.task_id);
                loadSavedFiles();
                showToast(`Gotowe: ${state.filename || "plik zapisany"}`);
            }

            // On hosted cloud servers or LAN devices, automatically trigger browser file save
            if (!isLocalHostClient && !autoTriggeredTasks.has(state.task_id)) {
                autoTriggeredTasks.add(state.task_id);
                const dlLink = card.querySelector('[data-role="download-link"]');
                if (dlLink) dlLink.click();
            }
        } else if (state.status === "error") {
            openStudioPillText.textContent = "Panel pobierania";
            barEl.classList.remove("progress-shimmer");
            barEl.classList.add("bg-red-600");
            pctEl.className = "text-sm font-mono-num font-bold text-red-400 shrink-0";
            pctEl.textContent = "Błąd";
            telemetryEl.classList.add("hidden");
            errorEl.textContent = state.error || "Wystąpił błąd podczas przetwarzania.";
            errorEl.classList.remove("hidden");
        }
    }

    function subscribeToTaskProgress(taskId) {
        const es = new EventSource(`/api/progress/${encodeURIComponent(taskId)}`);
        let finished = false;

        es.onmessage = (event) => {
            try {
                const state = JSON.parse(event.data);
                scheduleTaskCardUI(state);
                if (state.status === "completed" || state.status === "error") {
                    finished = true;
                    es.close();
                }
            } catch {
                // Ignore keepalive frames
            }
        };

        es.onerror = () => {
            es.close();
            if (!finished) {
                pollTaskFallback(taskId);
            }
        };
    }

    async function pollTaskFallback(taskId) {
        const timer = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${encodeURIComponent(taskId)}`);
                if (!res.ok) {
                    clearInterval(timer);
                    return;
                }
                const state = await res.json();
                scheduleTaskCardUI(state);
                if (state.status === "completed" || state.status === "error") {
                    clearInterval(timer);
                }
            } catch {
                clearInterval(timer);
            }
        }, 1000);
    }

    // 6. Local Downloads Folder Management & Delegated File Actions
    async function openDownloadsFolder(payload = {}) {
        try {
            const res = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json();
                showToast(err.detail || "Nie udało się otworzyć folderu.");
                return;
            }
            showToast("Otwarto folder w Eksploratorze Windows");
        } catch {
            showToast("Nie można otworzyć folderu zdalnie.");
        }
    }

    async function saveFileAsDialog(payload = {}) {
        try {
            const res = await fetch("/api/save-as", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json();
                showToast(err.detail || "Nie udało się zapisać kopii pliku.");
                return;
            }
            const data = await res.json();
            if (data.saved && data.path) {
                showToast(`Zapisano plik: ${data.path}`);
            }
        } catch {
            showToast("Plik znajduje się już w katalogu downloads/");
        }
    }

    if (!isLocalHostClient) {
        openFolderMainBtn.classList.add("hidden");
    }
    openFolderMainBtn.addEventListener("click", () => openDownloadsFolder({}));
    refreshFilesBtn.addEventListener("click", () => loadSavedFiles());

    savedFilesList.addEventListener("click", async (e) => {
        const selectBtn = e.target.closest("[data-select-file]");
        if (selectBtn && savedFilesList.contains(selectBtn)) {
            openDownloadsFolder({ filename: selectBtn.dataset.selectFile });
            return;
        }

        const saveLink = e.target.closest("[data-save-as]");
        if (saveLink && savedFilesList.contains(saveLink) && canUseNativeHost()) {
            e.preventDefault();
            saveFileAsDialog({ filename: saveLink.dataset.saveAs });
            return;
        }

        const delBtn = e.target.closest("[data-delete-file]");
        if (delBtn && savedFilesList.contains(delBtn)) {
            const fname = delBtn.dataset.deleteFile;
            if (!fname) return;
            const res = await fetch(`/api/downloads/${encodeURIComponent(fname)}`, {
                method: "DELETE",
            });
            if (res.ok) {
                showToast("Usunięto plik");
                loadSavedFiles();
            }
        }
    });

    async function loadSavedFiles() {
        try {
            const res = await fetch("/api/downloads");
            if (!res.ok) return;
            const data = await res.json();
            const files = data.files || [];
            const nativeHost = canUseNativeHost();

            filesCountBadge.textContent = String(files.length);

            if (files.length === 0) {
                savedFilesEmpty.classList.remove("hidden");
                savedFilesList.classList.add("hidden");
                savedFilesList.innerHTML = "";
                return;
            }

            savedFilesEmpty.classList.add("hidden");
            savedFilesList.classList.remove("hidden");

            savedFilesList.innerHTML = files
                .map((f) => {
                    const extColor = ["MP3", "M4A", "FLAC", "WAV"].includes(f.ext)
                        ? "bg-yellow-500/15 text-yellow-300 border-yellow-500/30"
                        : ["MKV", "WEBM"].includes(f.ext)
                        ? "bg-red-500/15 text-red-300 border-red-500/30"
                        : "bg-amber-500/15 text-amber-300 border-amber-500/30";

                    const encodedName = encodeURIComponent(f.filename);
                    return `
                        <div class="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                            <div class="flex items-center gap-3 min-w-0">
                                <span class="text-[11px] font-mono-num font-bold px-2 py-1 rounded-md border ${extColor} shrink-0">
                                    ${escapeHtml(f.ext)}
                                </span>
                                <div class="min-w-0">
                                    <p class="text-sm font-medium text-white truncate" title="${escapeHtml(f.filename)}">
                                        ${escapeHtml(f.filename)}
                                    </p>
                                    <p class="text-xs font-mono-num text-neutral-400">${escapeHtml(f.filesize_str)}</p>
                                </div>
                            </div>

                            <div class="flex items-center gap-2 shrink-0 self-end sm:self-center">
                                ${
                                    nativeHost
                                        ? `<button type="button" data-select-file="${escapeHtml(f.filename)}" title="Pokaż w Eksploratorze"
                                            class="p-2 rounded-full bg-white/[0.06] hover:bg-white/15 border border-white/15 text-white transition cursor-pointer">
                                            <svg class="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                                            </svg>
                                           </button>`
                                        : ""
                                }
                                <a href="/api/downloads/file/${encodedName}" download data-save-as="${escapeHtml(f.filename)}"
                                    class="px-4 py-1.5 rounded-full bg-amber-300 hover:bg-white text-xs font-extrabold text-black transition flex items-center gap-1.5 cursor-pointer">
                                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.3">
                                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" />
                                    </svg>
                                    <span>${nativeHost ? "Zapisz jako..." : "Pobierz na dysk"}</span>
                                </a>
                                <button type="button" data-delete-file="${escapeHtml(f.filename)}" title="Usuń plik z dysku"
                                    class="p-2 rounded-full bg-white/[0.06] hover:bg-red-950/80 border border-white/15 hover:border-red-500/40 text-neutral-300 hover:text-red-300 transition cursor-pointer">
                                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                </button>
                            </div>
                        </div>
                    `;
                })
                .join("");
        } catch {
            // Ignore initial load error
        }
    }

    // 7. Interactive Rockstar Poster Card CTA Buttons
    document.querySelectorAll("[data-card-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const action = btn.dataset.cardAction;
            if (action === "preset-mp4") {
                selectedCategory = "mp4";
                formatTabs.forEach((t) => t.classList.toggle("format-tab-active", t.dataset.format === "mp4"));
                pickDefaultVariantForCategory("mp4");
                renderQualityOptions();
                showToast("Aktywowano tryb Wideo MP4 / 4K Ultra HD");
            } else if (action === "preset-audio") {
                selectedCategory = "audio";
                formatTabs.forEach((t) => t.classList.toggle("format-tab-active", t.dataset.format === "audio"));
                pickDefaultVariantForCategory("audio");
                renderQualityOptions();
                showToast("Aktywowano tryb Audio MP3 320 / FLAC / WAV");
            } else if (action === "preset-extra") {
                extraOptionsPanel.classList.remove("hidden");
                toggleExtraChevron.style.transform = "rotate(180deg)";
                showToast("Włączono opcje wycinków czasowych, napisów i playlist");
            }

            if (currentMedia) {
                openStudioModal();
            } else {
                urlInput.focus();
            }
        });
    });

    // Initialize sequentially so adaptive mode flags are ready before file list renders
    (async () => {
        await checkHealth();
        loadSavedFiles();
    })();
})();
