// DOM Elements
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const loading = document.getElementById('loading');
const dashboard = document.getElementById('dashboard');
const searchResults = document.getElementById('search-results');
const resultsContainer = document.getElementById('results-container');
const aiInterpretation = document.getElementById('ai-interpretation');
const interpretationText = document.getElementById('interpretation-text');
const resultsSummary = document.getElementById('results-summary');
const summaryText = document.getElementById('summary-text');
const emptyState = document.getElementById('empty-state');
const errorState = document.getElementById('error-state');
const examples = document.getElementById('examples');
const searchContainer = document.getElementById('search-container');
const contentCenter = document.getElementById('content-center');
const heroText = document.getElementById('hero-text');

const modalBackdrop = document.getElementById('modal-backdrop');
const modalContent = document.getElementById('modal-content');
const closeModalBtn = document.getElementById('close-modal');

// State
let allMovies = [];

// Config: Curated Prompt Pool
const EXAMPLE_PROMPTS = [
    { icon: 'ghost', text: 'A24 Horror' },
    { icon: 'trending-up', text: 'High ROI Sci-Fi' },
    { icon: 'history', text: '90s Thrillers' },
    { icon: 'zap', text: 'Cyberpunk Action' },
    { icon: 'heart', text: 'Comfort Movies' },
    { icon: 'skull', text: 'Cult Classics' },
    { icon: 'search', text: 'Whodunnit' },
    { icon: 'rocket', text: 'Space Opera' },
    { icon: 'dollar-sign', text: 'Low Budget Hits' },
    { icon: 'brain-circuit', text: 'Mind Bending' }
];

function renderRandomExamples() {
    if (!examples) return;

    // Shuffle and pick 3
    const shuffled = [...EXAMPLE_PROMPTS].sort(() => 0.5 - Math.random());
    const selected = shuffled.slice(0, 3);

    examples.innerHTML = selected.map(ex => `
        <button class="example-btn px-5 py-2 rounded-full border border-white/5 bg-white/5 hover:bg-white/10 text-cream/40 hover:text-accent-gold text-[10px] tracking-[0.2em] uppercase transition-all flex items-center gap-2 group">
            <i data-lucide="${ex.icon}" class="w-3 h-3 text-accent-gold/50 group-hover:text-accent-gold transition-colors"></i>
            ${ex.text}
        </button>
    `).join('');

    lucide.createIcons();
}

// Event listeners
searchBtn.addEventListener('click', () => handleSearch());
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSearch();
});

if (examples) {
    examples.addEventListener('click', (e) => {
        const btn = e.target.closest('.example-btn');
        if (btn) {
            searchInput.value = btn.textContent.trim();
            handleSearch();
        }
    });
}

closeModalBtn.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeModal();
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    renderRandomExamples();
    lucide.createIcons();
});

// ===== LETTER-BY-LETTER ORACLE ANIMATION =====
function animateOracleText() {
    const titleEl = document.getElementById('loading-title');
    if (!titleEl) return;
    const titleText = 'Consulting the Oracle';
    titleEl.innerHTML = '';
    titleEl.classList.add('oracle-title-animated');
    for (let i = 0; i < titleText.length; i++) {
        const span = document.createElement('span');
        span.className = 'oracle-letter';
        span.style.animationDelay = `${i * 0.04}s`;
        span.textContent = titleText[i] === ' ' ? '\u00A0' : titleText[i];
        titleEl.appendChild(span);
    }
}

// ===== COLD START DETECTION =====
let backendReady = false;
let coldStartNotificationTimeout = null;

function showColdStartNotification() {
    let notification = document.getElementById('cold-start-notification');
    if (!notification) {
        notification = document.createElement('div');
        notification.id = 'cold-start-notification';
        notification.className = 'fixed top-4 left-1/2 -translate-x-1/2 z-50 glass-panel border border-accent-gold/30 rounded-xl px-6 py-4 flex items-center gap-4 animate-pulse';
        notification.innerHTML = `
            <div class="w-5 h-5 border-2 border-accent-gold/30 border-t-accent-gold rounded-full animate-spin"></div>
            <div>
                <p class="text-cream font-bold text-sm">Server is waking up...</p>
                <p class="text-cream/50 text-xs">This may take up to 60 seconds</p>
            </div>
        `;
        document.body.appendChild(notification);
    }
    notification.classList.remove('hidden');
}

function hideColdStartNotification() {
    if (coldStartNotificationTimeout) {
        clearTimeout(coldStartNotificationTimeout);
        coldStartNotificationTimeout = null;
    }
    const notification = document.getElementById('cold-start-notification');
    if (notification) notification.classList.add('hidden');
}

// Fast search with automatic cold-start retry
async function performSearch(query, attempt = 0) {
    const maxAttempts = 20; // 20 attempts * 3 seconds = 60 seconds max
    const retryDelay = 3000;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout per request

        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Search failed' }));
            throw new Error(err.detail || `Request failed (${response.status})`);
        }

        backendReady = true;
        hideColdStartNotification();
        return await response.json();

    } catch (error) {
        // Check if it's a network/timeout error that suggests cold start
        const isColdStartError = error.name === 'AbortError' ||
            error.message.includes('Failed to fetch') ||
            error.message.includes('NetworkError');

        if (isColdStartError && attempt < maxAttempts) {
            // Show cold-start notification only after first failure (delayed)
            if (attempt === 0) {
                coldStartNotificationTimeout = setTimeout(() => {
                    showColdStartNotification();
                }, 2000); // Show after 2s if still retrying
            }

            // Wait and retry
            await new Promise(resolve => setTimeout(resolve, retryDelay));
            return performSearch(query, attempt + 1);
        }

        // Real error, not cold start
        throw error;
    }
}

async function handleSearch(retryQuery = null) {
    if (retryQuery) {
        searchInput.value = retryQuery;
    }

    const query = searchInput.value.trim();
    if (!query) return;

    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Show loading animation IMMEDIATELY
    showLoading();

    try {
        const data = await performSearch(query);
        displayResults(data);
    } catch (error) {
        hideColdStartNotification();
        showError(error.message, query);
    }
}


function displayResults(data) {
    const progressEl = document.getElementById('loading-progress');
    if (progressEl) progressEl.style.width = "100%";

    setTimeout(() => {
        hideLoading();
        if (dashboard) dashboard.classList.add('hidden');
        searchResults.classList.remove('hidden');

        if (data.ai_interpretation) {
            interpretationText.textContent = data.ai_interpretation;
            aiInterpretation.classList.remove('hidden');
        }
        if (data.summary) {
            summaryText.textContent = data.summary;
            resultsSummary.classList.remove('hidden');
        }

        if (!data.results || data.results.length === 0) {
            emptyState.classList.remove('hidden');
            resultsContainer.innerHTML = '';
            return;
        }

        allMovies = [...data.results];
        resultsContainer.innerHTML = data.results.map((movie, index) => createBigCard(movie, index + 1, index)).join('');
        lucide.createIcons();
    }, 500);
}

function createBigCard(movie, rank, index) {
    const posterUrl = movie.poster_url || 'https://via.placeholder.com/300x450/0f172a/666?text=No+Poster';
    const delay = index * 0.12;
    const oracleScore = calculateOracleScore(movie);

    return `
    <div class="glass-panel rounded-none p-8 flex gap-8 relative group cursor-pointer hover:bg-white/[0.02] transition-all duration-700 result-card-animate"
         style="animation-delay: ${delay}s"
         onclick="openModal('${movie.tmdb_id}')">
        <div class="absolute -top-3 -left-3 text-cream/20 text-4xl serif italic select-none">
            ${rank.toString().padStart(2, '0')}
        </div>

        <div class="w-32 sm:w-48 flex-shrink-0">
            <img src="${posterUrl}" alt="${escapeHtml(movie.title)}"
                 class="shadow-2xl w-full aspect-[2/3] object-cover grayscale-[0.3] group-hover:grayscale-0 transition-all duration-1000"
                 loading="lazy">
        </div>

        <div class="flex-1 min-w-0 flex flex-col justify-center">
            <div class="flex justify-between items-start mb-4">
                <div class="min-w-0">
                    <h3 class="text-2xl sm:text-3xl font-bold text-cream tracking-tight group-hover:text-accent-gold transition-colors">${escapeHtml(movie.title)}</h3>
                    <div class="flex items-center gap-3 mt-2">
                        <p class="text-[10px] text-cream/40 uppercase tracking-[0.2em] font-bold">${movie.year || 'N/A'} — ${movie.runtime || '?'} MIN</p>
                        ${movie.performance && movie.performance !== 'Unknown' ? `
                        <span class="text-[9px] uppercase tracking-[0.2em] font-bold text-accent-gold">
                             [ ${movie.performance} ]
                        </span>` : ''}
                    </div>
                </div>
                ${movie.roi && movie.roi !== 'N/A' ? `
                <div class="text-right">
                    <p class="text-[8px] uppercase font-bold text-cream/20 tracking-widest mb-1">Yield</p>
                    <p class="text-lg font-bold text-cream serif">${movie.roi}</p>
                </div>` : ''}
            </div>

            ${movie.relevance_explanation ? `
            <p class="text-accent-gold/80 text-[11px] mb-4 uppercase tracking-wider leading-relaxed border-l border-accent-gold/30 pl-4 py-1">
                ${escapeHtml(movie.relevance_explanation)}
            </p>` : ''}

            <p class="text-cream/40 text-sm leading-relaxed line-clamp-2 max-w-xl">
                ${escapeHtml(movie.overview || 'Description not available.')}
            </p>

            <div class="flex flex-wrap gap-6 mt-6 items-center border-t border-white/5 pt-6">
                ${oracleScore ? `<div class="flex items-center gap-2 text-[10px] font-bold tracking-widest text-accent-gold uppercase"><i data-lucide="sparkles" class="w-3 h-3"></i><span>Oracle</span><span class="text-cream/80">${oracleScore}</span></div>` : ''}
                ${movie.imdb_rating ? `<div class="flex items-center gap-2 text-[10px] font-bold tracking-widest text-white/40 uppercase"><span>IMDb</span><span class="text-cream/80">${movie.imdb_rating}</span></div>` : ''}
                ${movie.rotten_tomatoes && movie.rotten_tomatoes !== 'N/A' ? `<div class="flex items-center gap-2 text-[10px] font-bold tracking-widest text-white/40 uppercase"><span>RT</span><span class="text-cream/80">${movie.rotten_tomatoes}</span></div>` : ''}
            </div>
        </div>
    </div>`;
}

async function openModal(id) {
    let movie = allMovies.find(m => m.tmdb_id == id);
    modalContent.innerHTML = `<div class="p-40 text-center"><div class="relative inline-block"><div class="w-12 h-12 border-2 border-accent-gold/20 border-t-accent-gold rounded-full animate-spin"></div></div></div>`;
    modalBackdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    try {
        const response = await fetch(`/api/details/${id}`);
        if (response.ok) movie = await response.json();
    } catch (err) { console.error(err); }

    if (!movie) return;

    modalContent.innerHTML = renderModalContent(movie);
    lucide.createIcons();
}

function closeModal() {
    modalBackdrop.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

// --- LOADING UI LOGIC ---
let statusInterval;

const loadingSteps = [
    { text: "Establishing Secure Link...", percent: "15%" },
    { text: "Contacting Movie API...", percent: "30%" },
    { text: "Parsing Search Query...", percent: "45%" },
    { text: "Scanning Cinematic Multiverse...", percent: "60%" },
    { text: "Cross-referencing Ratings...", percent: "75%" },
    { text: "Calculating ROI & Budget...", percent: "85%" },
    { text: "Finalizing Oracle Prediction...", percent: "95%" }
];

function cycleStatusMessages() {
    const subtitleEl = document.getElementById('loading-subtitle');
    const progressEl = document.getElementById('loading-progress');
    if (!subtitleEl || !progressEl) return;

    let index = 0;
    progressEl.style.width = '0%';
    subtitleEl.textContent = 'Initializing...';
    subtitleEl.className = 'text-accent-gold/70 uppercase tracking-[0.2em] text-[10px] font-bold animate-pulse';

    if (statusInterval) clearInterval(statusInterval);

    setTimeout(() => {
        subtitleEl.textContent = loadingSteps[0].text;
        progressEl.style.width = loadingSteps[0].percent;
    }, 50);

    statusInterval = setInterval(() => {
        index++;
        if (index >= loadingSteps.length) {
            clearInterval(statusInterval);
            return;
        }
        subtitleEl.textContent = loadingSteps[index].text;
        progressEl.style.width = loadingSteps[index].percent;
    }, 800);
}

function showLoading() {
    const mainContent = document.getElementById('main-content');
    if (mainContent) mainContent.classList.remove('hidden');
    loading.classList.remove('hidden');
    if (dashboard) dashboard.classList.add('hidden');
    searchResults.classList.add('hidden');
    emptyState.classList.add('hidden');
    errorState.classList.add('hidden');
    document.body.classList.add('results-mode');
    animateOracleText();
    cycleStatusMessages();
    lucide.createIcons();
}

function hideLoading() {
    loading.classList.add('hidden');
    if (statusInterval) clearInterval(statusInterval);
}

function showError(message, query) {
    hideLoading();
    const mainContent = document.getElementById('main-content');
    if (mainContent) mainContent.classList.remove('hidden');
    const retryCall = query ? `handleSearch('${escapeHtml(query)}')` : 'handleSearch()';

    errorState.innerHTML = `
        <div class="glass-panel border-red-500/20 rounded-2xl p-8 text-center max-w-2xl mx-auto mt-12">
            <div class="bg-red-500/20 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                <i data-lucide="alert-octagon" class="w-8 h-8 text-red-500"></i>
            </div>
            <h3 class="text-xl font-bold text-white mb-2">Oracle Interference</h3>
            <p class="text-slate-400 text-sm mb-6">${escapeHtml(message)}</p>
            <button onclick="${retryCall}" class="bg-white/5 hover:bg-white/10 px-6 py-2 rounded-xl text-white text-sm font-bold transition-colors">Retry</button>
        </div>`;
    errorState.classList.remove('hidden');
    lucide.createIcons();
}

