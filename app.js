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
let hasTransitioned = false;

const PROMPT_POOL = [
    { icon: "ghost", text: "A24 Horror" },
    { icon: "trending-up", text: "High ROI Sci-Fi" },
    { icon: "history", text: "90s Thrillers" },
    { icon: "rocket", text: "Space Operas" },
    { icon: "skull", text: "Slasher Flops" },
    { icon: "heart", text: "Indie Romance" },
    { icon: "sword", text: "Epic Fantasy" },
    { icon: "camera", text: "Found Footage" },
    { icon: "brain", text: "Psychological Mindbenders" },
    { icon: "laugh", text: "Dark Comedies" },
    { icon: "zap", text: "Cyberpunk Cult Classics" }
];

function renderRandomExamples() {
    const container = document.getElementById('examples');
    if (!container) return;

    // Shuffle and pick 3
    const shuffled = [...PROMPT_POOL].sort(() => 0.5 - Math.random());
    const selected = shuffled.slice(0, 3);

    container.innerHTML = selected.map(p => `
        <button class="example-btn px-5 py-2 rounded-full border border-white/5 bg-white/5 hover:bg-white/10 text-cream/40 hover:text-accent-gold text-[10px] tracking-[0.2em] uppercase transition-all flex items-center gap-2 group">
            <i data-lucide="${p.icon}" class="w-3 h-3 text-accent-gold/50 group-hover:text-accent-gold transition-colors"></i>
            ${p.text}
        </button>
    `).join('');

    // Refresh icons since we just added new HTML
    lucide.createIcons();
}

// Event listeners
searchBtn.addEventListener('click', handleSearch);
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSearch();
});

examples.addEventListener('click', (e) => {
    const btn = e.target.closest('.example-btn');
    if (btn) {
        searchInput.value = btn.textContent.trim();
        handleSearch();
    }
});

closeModalBtn.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeModal();
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    renderRandomExamples();
    lucide.createIcons();
});

// ===== SMOOTH SLIDE-TO-TOP TRANSITION =====
// REMOVED PER USER REQUEST

// ===== LETTER-BY-LETTER ORACLE ANIMATION =====
function animateOracleText() {
    const titleEl = document.getElementById('loading-title');
    if (!titleEl) return;

    const titleText = 'Consulting the Oracle';

    // Build letter-by-letter HTML for title
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

async function handleSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    transitionToResults(); // REMOVED
    window.scrollTo({ top: 0, behavior: 'smooth' });
    showLoading();

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Search failed' }));
            throw new Error(err.detail || `Request failed (${response.status})`);
        }

        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError(error.message);
    }
}

function renderMovieGrid(container, movies) {
    if (!movies || movies.length === 0) {
        container.innerHTML = '<p class="col-span-full text-slate-500 text-center py-8">No movies found.</p>';
        return;
    }

    container.innerHTML = movies.map(movie => `
        <div class="movie-card group cursor-pointer" onclick="openModal('${movie.tmdb_id}')">
            <div class="relative aspect-[2/3] rounded-sm overflow-hidden mb-4 border border-white/5 bg-black">
                <img src="${movie.poster_url || 'https://via.placeholder.com/300x450/0f172a/666?text=No+Poster'}"
                     alt="${escapeHtml(movie.title)}"
                     class="w-full h-full object-cover opacity-80 group-hover:opacity-100 group-hover:scale-105 transition-all duration-1000"
                     loading="lazy">
                <div class="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black to-transparent"></div>
            </div>
            <h4 class="text-xs font-bold text-cream/90 uppercase tracking-widest leading-relaxed group-hover:text-accent-gold transition-colors line-clamp-2">${escapeHtml(movie.title)}</h4>
            <p class="text-[10px] text-cream/30 serif italic mt-1">${movie.year || 'TBA'}</p>
        </div>
    `).join('');
    lucide.createIcons();
}

function displayResults(data) {
    // 1. Force progress bar to 100%
    const progressEl = document.getElementById('loading-progress');
    if (progressEl) progressEl.style.width = "100%";

    // 2. Wait 500ms before showing results so the animation plays
    setTimeout(() => {
        hideLoading();
        if (dashboard) dashboard.classList.add('hidden');
        searchResults.classList.remove('hidden');

        // Show AI interpretation with animation
        if (data.ai_interpretation) {
            interpretationText.textContent = data.ai_interpretation;
            aiInterpretation.classList.remove('hidden');
        }

        // Show summary
        if (data.summary) {
            summaryText.textContent = data.summary;
            resultsSummary.classList.remove('hidden');
        }

        // Render cards
        if (!data.results || data.results.length === 0) {
            emptyState.classList.remove('hidden');
            resultsContainer.innerHTML = '';
            return;
        }

        allMovies = [...allMovies, ...data.results];

        // Render with staggered animation
        resultsContainer.innerHTML = data.results.map((movie, index) => createBigCard(movie, index + 1, index)).join('');
        lucide.createIcons();
    }, 500); // End Timeout
}

function calculateOracleScore(movie) {
    // 1. TRUST THE AI (Context-Aware Score)
    // If the AI gave us a specific score for this search, use it immediately.
    if (movie.oracle_score !== undefined && movie.oracle_score !== null) {
        return movie.oracle_score;
    }

    // 2. SMARTER FALLBACK (Statistical Score)
    // Used for "Trending" or "Discover" pages where AI hasn't run.

    let scoreSum = 0;
    let weightSum = 0;

    // Metacritic (High Authority) - Weight: 3.0
    if (movie.metascore && movie.metascore !== 'N/A') {
        const val = parseInt(movie.metascore);
        if (!isNaN(val)) {
            scoreSum += val * 3;
            weightSum += 3;
        }
    }

    // Rotten Tomatoes (Consensus) - Weight: 2.5
    if (movie.rotten_tomatoes && movie.rotten_tomatoes !== 'N/A') {
        const val = parseInt(movie.rotten_tomatoes);
        if (!isNaN(val)) {
            scoreSum += val * 2.5;
            weightSum += 2.5;
        }
    }

    // IMDb (Audience) - Weight: 2.0
    if (movie.imdb_rating && movie.imdb_rating !== 'N/A') {
        const val = parseFloat(movie.imdb_rating);
        if (!isNaN(val)) {
            scoreSum += (val * 10) * 2.0;
            weightSum += 2.0;
        }
    }

    // TMDb (Data Source) - Weight: 1.0
    if (movie.tmdb_rating) {
        scoreSum += (movie.tmdb_rating * 10) * 1.0;
        weightSum += 1.0;
    }

    if (weightSum === 0) return null;

    let finalScore = scoreSum / weightSum;

    // 3. THE "CULT CLASSIC" BONUS
    // If Audience (IMDb) loves it much more than Critics (Metascore), boost it.
    // This fixes the "Venom" or "Mario Movie" problem.
    if (movie.imdb_rating && movie.metascore && movie.metascore !== 'N/A') {
        const imdbVal = parseFloat(movie.imdb_rating) * 10;
        const metaVal = parseInt(movie.metascore);

        if (imdbVal > metaVal + 15) {
            // Audience likes it 15% more than critics -> Add ~5 points
            finalScore += 5;
        }
    }

    // 4. BLOCKBUSTER BONUS
    // If it made over $1B, it has cultural impact regardless of reviews.
    if (movie.revenue && typeof movie.revenue === 'string') {
        const revVal = parseInt(movie.revenue.replace(/[^0-9]/g, ''));
        if (revVal >= 1000000000) finalScore += 3;
    }

    return Math.min(100, Math.round(finalScore));
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

function getPerfColorClass(color) {
    const maps = {
        'red': 'bg-red-500/10 text-red-500 border border-red-500/20',
        'orange': 'bg-orange-500/10 text-orange-500 border border-orange-500/20',
        'amber': 'bg-amber-500/10 text-amber-500 border border-amber-500/20',
        'emerald': 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20',
        'indigo': 'bg-indigo-500/10 text-indigo-500 border border-indigo-500/20',
        'slate': 'bg-slate-500/10 text-slate-500 border border-slate-500/20'
    };
    return maps[color] || maps['slate'];
}

async function openModal(id) {
    let movie = allMovies.find(m => m.tmdb_id == id);

    modalContent.innerHTML = `<div class="p-40 text-center"><div class="relative inline-block"><div class="w-12 h-12 border-2 border-accent-gold/20 border-t-accent-gold rounded-full animate-spin"></div></div></div>`;
    modalBackdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    try {
        const response = await fetch(`/api/details/${id}`);
        if (response.ok) {
            movie = await response.json();
        }
    } catch (err) {
        console.error("Modal fetch error:", err);
    }

    if (!movie) return;

    const oracleScore = calculateOracleScore(movie);
    const posterUrl = movie.poster_url || 'https://via.placeholder.com/300x450/0f172a/666?text=No+Poster';
    const backdropUrl = movie.backdrop_url || posterUrl;

    modalContent.innerHTML = `
        <div class="relative">
            <div class="h-80 sm:h-[30rem] relative overflow-hidden">
                <img src="${backdropUrl}" class="w-full h-full object-cover opacity-20 scale-105 blur-sm">
                <div class="absolute inset-0 bg-gradient-to-t from-[#0a0a0c] via-transparent to-transparent"></div>
            </div>

            <div class="px-8 sm:px-16 pb-20 -mt-60 relative">
                <div class="flex flex-col md:flex-row gap-12 items-end">
                    <img src="${posterUrl}" class="w-56 sm:w-80 shadow-[0_40px_80px_rgba(0,0,0,0.8)] border border-white/5 shrink-0">
                    <div class="flex-1 pb-4">
                        <div class="inline-block border border-accent-gold/40 text-accent-gold text-[9px] uppercase tracking-[0.3em] px-3 py-1 mb-6">
                            ${movie.performance || 'Production Study'}
                        </div>
                        <h2 class="text-5xl sm:text-8xl font-bold text-cream mb-6 tracking-tight leading-none">${escapeHtml(movie.title)}</h2>
                        <div class="flex flex-wrap gap-6 text-[10px] uppercase tracking-[0.2em] font-bold text-cream/40 items-center">
                            <span>${movie.year || 'N/A'}</span>
                            <span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span>${movie.runtime || '?'} min</span>
                            <span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span class="text-accent-gold italic serif normal-case tracking-normal text-sm">${escapeHtml(movie.genres || 'N/A')}</span>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-16 mt-16">
                    <div class="lg:col-span-2 space-y-12">
                        <div>
                            <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-6">The Synopsis</h4>
                            <p class="text-2xl text-cream/80 leading-relaxed serif italic">${escapeHtml(movie.overview || 'Description not available.')}</p>
                        </div>

                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-12 pt-8 border-t border-white/5">
                            <div>
                                <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Director</h4>
                                <p class="text-xl text-cream font-medium">${escapeHtml(movie.director || 'Unknown')}</p>
                            </div>
                            <div>
                                <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Principals</h4>
                                <p class="text-xl text-cream font-medium">${escapeHtml(movie.actors || 'Unknown')}</p>
                            </div>
                        </div>
                    </div>

                    <div class="space-y-10">
                        <div class="border-l border-white/5 pl-8 py-2">
                             <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-8">Production Analysis</h4>
                             <div class="space-y-6">
                                ${buildDetailRow('Expenditure', movie.budget)}
                                ${buildDetailRow('Market Yield', movie.revenue)}
                                ${movie.roi && movie.roi !== 'N/A' ? `
                                <div class="pt-6 mt-6 border-t border-white/5">
                                    <p class="text-[9px] font-bold text-accent-gold uppercase tracking-[0.3em] mb-2">Yield Multiple</p>
                                    <p class="text-4xl font-bold text-cream serif">${movie.roi}</p>
                                </div>` : ''}
                             </div>
                        </div>

                        <div class="flex gap-4 border-t border-white/5 pt-10">
                             ${buildRatingBox('Oracle', oracleScore, true)}
                             ${buildRatingBox('IMDb', movie.imdb_rating)}
                             ${buildRatingBox('RT', movie.rotten_tomatoes)}
                             ${buildRatingBox('Meta', movie.metascore)}
                        </div>


                        ${movie.streaming ? `
                        <div class="pt-8 border-t border-white/5">
                            <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Distribution</h4>
                            <p class="text-cream/60 text-xs leading-relaxed uppercase tracking-widest">${escapeHtml(movie.streaming)}</p>
                        </div>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;

    lucide.createIcons();
}

function buildRatingBox(label, value, isOracle = false) {
    if (!value || value === 'N/A') return '';
    const labelClass = isOracle ? 'text-accent-gold' : 'text-cream/20';
    const borderClass = isOracle ? 'border-accent-gold/20 bg-accent-gold/5' : 'border-white/5';

    return `
        <div class="flex-1 border ${borderClass} p-4 text-center">
            <p class="text-[8px] font-bold ${labelClass} uppercase mb-2 tracking-widest">${label}</p>
            <p class="text-sm font-bold text-cream/80">${value}</p>
        </div>
    `;
}


function buildDetailRow(label, value) {
    if (!value || value === 'N/A') return '';
    return `
        <div class="flex justify-between items-center text-[10px] uppercase tracking-widest">
            <span class="text-cream/20 font-bold">${label}</span>
            <span class="text-cream/80 font-bold">${escapeHtml(value)}</span>
        </div>
    `;
}

function closeModal() {
    modalBackdrop.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

// --- NEW LOADING LOGIC ---
let statusInterval;

// Pair messages with percentages
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
    const progressEl = document.getElementById('loading-progress'); // Get the bar
    if (!subtitleEl || !progressEl) return;

    let index = 0;

    // Initial State - Reset explicitly to 0% first to allow transition
    progressEl.style.width = '0%';
    subtitleEl.textContent = 'Initializing...';

    // Style the text
    subtitleEl.className = 'text-accent-gold/70 uppercase tracking-[0.2em] text-[10px] font-bold animate-pulse';

    if (statusInterval) clearInterval(statusInterval);

    // Small delay to allow the 0% width to apply before jumping to first step
    setTimeout(() => {
        subtitleEl.textContent = loadingSteps[0].text;
        progressEl.style.width = loadingSteps[0].percent; // Set initial width
    }, 50);

    statusInterval = setInterval(() => {
        index++;

        // Stop incrementing if we reach the end (don't loop back to 0%)
        if (index >= loadingSteps.length) {
            clearInterval(statusInterval);
            return;
        }

        subtitleEl.textContent = loadingSteps[index].text;
        progressEl.style.width = loadingSteps[index].percent; // Update width
    }, 800);
}

function showLoading() {
    loading.classList.remove('hidden');
    if (dashboard) dashboard.classList.add('hidden');
    searchResults.classList.add('hidden');
    emptyState.classList.add('hidden');
    errorState.classList.add('hidden');

    // 1. Animate the Title (Keep your existing Oracle text effect)
    animateOracleText();

    // 2. Start the new Status Cycle (Replaces the static subtitle)
    cycleStatusMessages();

    lucide.createIcons();
}

function hideLoading() {
    loading.classList.add('hidden');
    // Stop the text cycle so it doesn't keep running in the background
    if (statusInterval) clearInterval(statusInterval);
}

function showError(message) {
    hideLoading();
    errorState.innerHTML = `
        <div class="glass-panel border-red-500/20 rounded-2xl p-8 text-center max-w-2xl mx-auto mt-12">
            <div class="bg-red-500/20 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                <i data-lucide="alert-octagon" class="w-8 h-8 text-red-500"></i>
            </div>
            <h3 class="text-xl font-bold text-white mb-2">Oracle Interference</h3>
            <p class="text-slate-400 text-sm mb-6">${escapeHtml(message)}</p>
            <button onclick="handleSearch()" class="bg-white/5 hover:bg-white/10 px-6 py-2 rounded-xl text-white text-sm font-bold transition-colors">Retry</button>
        </div>`;
    errorState.classList.remove('hidden');
    lucide.createIcons();
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
