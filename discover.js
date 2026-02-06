// DOM Elements
const modalBackdrop = document.getElementById('modal-backdrop');
const modalContent = document.getElementById('modal-content');
const closeModalBtn = document.getElementById('close-modal');

// State
let allMovies = [];

// Init
document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    await loadDiscoverContent();
    setupGenreButtons();
    setupStudioButtons();
});

// Modal handlers
closeModalBtn.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeModal();
});

async function loadDiscoverContent() {
    try {
        const response = await fetch('/api/discover');
        if (!response.ok) throw new Error('Failed to fetch discover data');

        const data = await response.json();

        renderMovieGrid('trending-grid', data.trending);
        renderMovieGrid('now-playing-grid', data.now_playing);
        renderMovieGrid('top-rated-grid', data.top_rated);
        renderMovieGrid('upcoming-grid', data.upcoming);

        // Store all movies for modal access
        allMovies = [
            ...data.trending,
            ...data.now_playing,
            ...data.top_rated,
            ...data.upcoming
        ];

    } catch (error) {
        console.error('Error loading discover content:', error);
        ['trending-grid', 'now-playing-grid', 'top-rated-grid', 'upcoming-grid'].forEach(id => {
            document.getElementById(id).innerHTML = `
                <p class="col-span-full text-cream/40 text-center py-8">Failed to load movies.</p>
            `;
        });
    }
}

function setupGenreButtons() {
    const genreChips = document.querySelectorAll('.genre-chip');
    genreChips.forEach(chip => {
        chip.addEventListener('click', async (e) => {
            const btn = e.currentTarget;

            // Add active to current
            btn.classList.add('chip-active');

            const genreId = btn.dataset.genre;
            await loadGenreMovies(genreId, btn.textContent.trim());
        });
    });
}

function setupStudioButtons() {
    const studioChips = document.querySelectorAll('.studio-chip');
    studioChips.forEach(chip => {
        chip.addEventListener('click', async (e) => {
            const btn = e.currentTarget;

            // Add active to current
            btn.classList.add('chip-active');

            const companyId = btn.dataset.company;
            await loadStudioMovies(companyId, btn.textContent.trim());
        });
    });
}

async function loadGenreMovies(genreId, genreName) {
    // Scroll to trending section and replace it with genre results
    const trendingSection = document.querySelector('#trending-grid').closest('section');
    const trendingTitle = trendingSection.querySelector('h2');
    const trendingGrid = document.getElementById('trending-grid');

    trendingTitle.textContent = genreName;
    trendingGrid.innerHTML = Array(10).fill(0).map(() =>
        '<div class="loading-shimmer aspect-[2/3] rounded-sm bg-white/5"></div>'
    ).join('');

    trendingSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const response = await fetch(`/api/genre/${genreId}`);
        if (!response.ok) throw new Error('Failed to fetch genre movies');

        const data = await response.json();
        renderMovieGrid('trending-grid', data.results);

        // Add genre movies to allMovies for modal
        allMovies = [...allMovies, ...data.results];
    } catch (error) {
        console.error('Error loading genre:', error);
        trendingGrid.innerHTML = `<p class="col-span-full text-cream/40 text-center py-8">Failed to load ${genreName} movies.</p>`;
    }
}

async function loadStudioMovies(companyId, companyName) {
    // Scroll to trending section and replace it with studio results
    const trendingSection = document.querySelector('#trending-grid').closest('section');
    const trendingTitle = trendingSection.querySelector('h2');
    const trendingGrid = document.getElementById('trending-grid');

    trendingTitle.textContent = companyName;
    trendingGrid.innerHTML = Array(10).fill(0).map(() =>
        '<div class="loading-shimmer aspect-[2/3] rounded-sm bg-white/5"></div>'
    ).join('');

    trendingSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const response = await fetch(`/api/company/${companyId}`);
        if (!response.ok) throw new Error('Failed to fetch studio movies');

        const data = await response.json();
        renderMovieGrid('trending-grid', data.results);

        // Add studio movies to allMovies for modal
        allMovies = [...allMovies, ...data.results];
    } catch (error) {
        console.error('Error loading studio:', error);
        trendingGrid.innerHTML = `<p class="col-span-full text-cream/40 text-center py-8">Failed to load ${companyName} movies.</p>`;
    }
}

function calculateOracleScore(movie) {
    // 1. SMART ORACLE SCORE (AI-driven)
    if (movie.ai_score !== undefined && movie.ai_score !== null) {
        return movie.ai_score;
    }

    // 2. Statistical Fallback
    let components = [];

    // On movie objects from discover, use tmdb_rating if primary ratings aren't present
    if (movie.imdb_rating && movie.imdb_rating !== 'N/A') {
        const val = parseFloat(movie.imdb_rating);
        if (!isNaN(val)) components.push(val * 10);
    }
    if (movie.rotten_tomatoes && movie.rotten_tomatoes !== 'N/A') {
        const val = parseInt(movie.rotten_tomatoes);
        if (!isNaN(val)) components.push(val);
    }
    if (movie.metascore && movie.metascore !== 'N/A') {
        const val = parseInt(movie.metascore);
        if (!isNaN(val)) components.push(val);
    }
    if (movie.tmdb_rating) {
        components.push(movie.tmdb_rating * 10);
    }

    if (components.length === 0) return null;

    let baseScore = components.reduce((a, b) => a + b, 0) / components.length;

    // 3. Financial Modifiers
    let modifier = 0;

    // ROI Modifier
    if (movie.roi && movie.roi !== 'N/A') {
        const roiVal = parseFloat(movie.roi);
        if (!isNaN(roiVal)) {
            if (roiVal >= 4) modifier += 5;
            else if (roiVal >= 2.5) modifier += 2;
            else if (roiVal < 1) modifier -= 5;
        }
    }

    // Revenue Modifier
    if (movie.revenue && movie.revenue !== 'N/A') {
        const revString = String(movie.revenue).replace(/[^0-9]/g, '');
        const revVal = parseInt(revString);
        if (!isNaN(revVal)) {
            if (revVal >= 1000000000) modifier += 5;
            else if (revVal >= 500000000) modifier += 2;
        }
    }

    return Math.min(100, Math.max(0, Math.round(baseScore + modifier)));
}


function renderMovieGrid(containerId, movies) {
    const container = document.getElementById(containerId);
    if (!movies || movies.length === 0) {
        container.innerHTML = '<p class="col-span-full text-cream/40 text-center py-8">No movies found.</p>';
        return;
    }

    container.innerHTML = movies.map((movie, index) => {
        const oracleScore = calculateOracleScore(movie);
        return `
        <div class="movie-card group cursor-pointer animate-fade-in-up"
             style="animation-delay: ${index * 0.05}s"
             onclick="openModal(${movie.tmdb_id})">

            <div class="relative aspect-[2/3] rounded-sm overflow-hidden mb-4 border border-white/5 bg-black">
                <img src="${movie.poster_url || 'https://via.placeholder.com/300x450/0f172a/666?text=No+Poster'}"
                     alt="${escapeHtml(movie.title)}"
                     class="w-full h-full object-cover opacity-80 group-hover:opacity-100 group-hover:scale-110 transition-all duration-1000"
                     loading="lazy">
                <div class="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black to-transparent"></div>

                ${movie.tmdb_rating ? `
                <div class="absolute top-2 right-2 bg-black/70 backdrop-blur-sm px-2 py-1 rounded text-[10px] font-bold text-accent-gold">
                    ★ ${movie.tmdb_rating.toFixed(1)}
                </div>` : ''}
            </div>
            <h4 class="text-xs font-bold text-cream/90 uppercase tracking-widest leading-relaxed group-hover:text-accent-gold transition-colors line-clamp-2">
                ${escapeHtml(movie.title)}
            </h4>
            <div class="flex items-center justify-between mt-1">
                <p class="text-[10px] text-cream/30">${movie.year || 'TBA'}</p>
                ${oracleScore ? `
                <div class="flex items-center gap-1">
                    <i data-lucide="sparkles" class="w-2.5 h-2.5 text-accent-gold/60"></i>
                    <span class="text-[9px] font-bold text-accent-gold/80 uppercase tracking-tighter">${oracleScore}</span>
                </div>` : ''}
            </div>
        </div>
    `}).join('');


    lucide.createIcons();
}

async function openModal(id) {
    let movie = allMovies.find(m => m.tmdb_id == id);

    modalContent.innerHTML = `
        <div class="p-40 text-center">
            <div class="relative inline-block">
                <div class="w-12 h-12 border-2 border-accent-gold/20 border-t-accent-gold rounded-full animate-spin"></div>
            </div>
        </div>`;
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
                        ${movie.performance ? `
                        <div class="inline-block border border-accent-gold/40 text-accent-gold text-[9px] uppercase tracking-[0.3em] px-3 py-1 mb-6">
                            ${movie.performance}
                        </div>` : ''}
                        <h2 class="text-5xl sm:text-8xl font-bold text-cream mb-6 tracking-tight leading-none font-prestige">${escapeHtml(movie.title)}</h2>
                        <div class="flex flex-wrap gap-6 text-[10px] uppercase tracking-[0.2em] font-bold text-cream/40 items-center">
                            <span>${movie.year || 'N/A'}</span>
                            <span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span>${movie.runtime || '?'} min</span>
                            ${movie.genres ? `
                            <span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span class="text-accent-gold italic serif normal-case tracking-normal text-sm">${escapeHtml(movie.genres)}</span>
                            ` : ''}
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-3 gap-16 mt-16">
                    <div class="lg:col-span-2 space-y-12">
                        ${movie.overview ? `
                        <div>
                            <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-6">The Synopsis</h4>
                            <p class="text-2xl text-cream/80 leading-relaxed serif italic">${escapeHtml(movie.overview)}</p>
                        </div>` : ''}

                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-12 pt-8 border-t border-white/5">
                            ${movie.director ? `
                            <div>
                                <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Director</h4>
                                <p class="text-xl text-cream font-medium">${escapeHtml(movie.director)}</p>
                            </div>` : ''}
                            ${movie.actors ? `
                            <div>
                                <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Principals</h4>
                                <p class="text-xl text-cream font-medium">${escapeHtml(movie.actors)}</p>
                            </div>` : ''}
                        </div>
                    </div>

                    <div class="space-y-10">
                        ${movie.budget || movie.revenue || movie.roi ? `
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
                        </div>` : ''}

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

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
