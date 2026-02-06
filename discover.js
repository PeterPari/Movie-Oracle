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
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<p class="col-span-full text-cream/40 text-center py-8">Failed to load movies.</p>`;
        });
    }
}

function setupGenreButtons() {
    const genreChips = document.querySelectorAll('.genre-chip');
    genreChips.forEach(chip => {
        chip.addEventListener('click', async (e) => {
            const btn = e.currentTarget;
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
            btn.classList.add('chip-active');
            const companyId = btn.dataset.company;
            await loadStudioMovies(companyId, btn.textContent.trim());
        });
    });
}

async function loadGenreMovies(genreId, genreName) {
    const trendingGrid = document.getElementById('trending-grid');
    if (!trendingGrid) return;
    const trendingSection = trendingGrid.closest('section');
    const trendingTitle = trendingSection.querySelector('h2');

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
        allMovies = [...allMovies, ...data.results];
    } catch (error) {
        console.error('Error loading genre:', error);
        trendingGrid.innerHTML = `<p class="col-span-full text-cream/40 text-center py-8">Failed to load ${genreName} movies.</p>`;
    }
}

async function loadStudioMovies(companyId, companyName) {
    const trendingGrid = document.getElementById('trending-grid');
    if (!trendingGrid) return;
    const trendingSection = trendingGrid.closest('section');
    const trendingTitle = trendingSection.querySelector('h2');

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
        allMovies = [...allMovies, ...data.results];
    } catch (error) {
        console.error('Error loading studio:', error);
        trendingGrid.innerHTML = `<p class="col-span-full text-cream/40 text-center py-8">Failed to load ${companyName} movies.</p>`;
    }
}

function renderMovieGrid(containerId, movies) {
    const container = document.getElementById(containerId);
    if (!container) return;
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
    modalContent.innerHTML = `<div class="p-40 text-center"><div class="w-12 h-12 border-2 border-accent-gold/20 border-t-accent-gold rounded-full animate-spin mx-auto"></div></div>`;
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

