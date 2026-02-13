// ===== SHARED UTILITIES =====

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function calculateOracleScore(movie) {
    const baseScore = Number(movie.oracle_score);
    if (Number.isFinite(baseScore)) return Math.max(0, Math.min(100, Math.round(baseScore)));

    const toNumber = (val) => {
        if (val === null || val === undefined) return null;
        if (typeof val === 'number') return Number.isFinite(val) ? val : null;
        if (typeof val === 'string') {
            if (val.trim().toUpperCase() === 'N/A') return null;
            const cleaned = val.replace(/[^0-9.]/g, '');
            const num = parseFloat(cleaned);
            return Number.isFinite(num) ? num : null;
        }
        return null;
    };

    const metascore = toNumber(movie.metascore); // 0-100
    const rottenTomatoes = toNumber(movie.rotten_tomatoes); // 0-100
    const imdb = toNumber(movie.imdb_rating); // 0-10
    const tmdb = toNumber(movie.tmdb_rating); // 0-10

    let scoreSum = 0;
    let weightSum = 0;

    if (metascore !== null) { scoreSum += metascore * 3.0; weightSum += 3.0; }
    if (rottenTomatoes !== null) { scoreSum += rottenTomatoes * 2.5; weightSum += 2.5; }
    if (imdb !== null) { scoreSum += (imdb * 10) * 2.0; weightSum += 2.0; }
    if (tmdb !== null) { scoreSum += (tmdb * 10) * 1.5; weightSum += 1.5; }

    if (weightSum === 0) return null;

    const finalScore = scoreSum / weightSum;
    return Math.max(0, Math.min(100, Math.round(finalScore)));
}

function renderPeopleLinks(links, fallbackStr) {
    if (links && links.length > 0) {
        return links.map(p => {
            const name = escapeHtml(p.name);
            if (p.imdb_url) {
                return `<a href="${escapeHtml(p.imdb_url)}" target="_blank" rel="noopener" class="text-cream hover:text-accent-gold transition-colors underline underline-offset-4 decoration-cream/20 hover:decoration-accent-gold/50">${name}</a>`;
            }
            return name;
        }).join(', ');
    }
    return escapeHtml(fallbackStr || '');
}

function buildRatingBox(label, value, isOracle = false) {
    if (!value || value === 'N/A') return '';
    const labelClass = isOracle ? 'text-accent-gold' : 'text-cream/20';
    const borderClass = isOracle ? 'border-accent-gold/20 bg-accent-gold/5' : 'border-white/5';
    return `<div class="flex-1 border ${borderClass} p-4 text-center"><p class="text-[8px] font-bold ${labelClass} uppercase mb-2 tracking-widest">${label}</p><p class="text-sm font-bold text-cream/80">${value}</p></div>`;
}

function buildDetailRow(label, value) {
    if (!value || value === 'N/A') return '';
    return `<div class="flex justify-between items-center text-[10px] uppercase tracking-widest"><span class="text-cream/20 font-bold">${label}</span><span class="text-cream/80 font-bold">${escapeHtml(value)}</span></div>`;
}

// ===== WHERE TO WATCH =====

function renderWatchProviders(movie) {
    const wp = movie.watch_providers;
    if (!wp) return '';

    const hasAny = (wp.flatrate && wp.flatrate.length) || (wp.rent && wp.rent.length) || (wp.buy && wp.buy.length);
    if (!hasAny) return '';

    const watchLink = wp.link || '#';

    function renderGroup(label, providers) {
        if (!providers || !providers.length) return '';
        return `
            <div class="mb-6">
                <p class="text-[8px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-3">${label}</p>
                <div class="flex flex-wrap gap-3">
                    ${providers.map(p => `
                        <a href="${escapeHtml(watchLink)}" target="_blank" rel="noopener" title="${escapeHtml(p.name)}"
                           class="group/prov relative">
                            <img src="${escapeHtml(p.logo_url)}" alt="${escapeHtml(p.name)}"
                                 class="w-10 h-10 rounded-lg object-cover border border-white/10 group-hover/prov:border-accent-gold/50 transition-all duration-300 group-hover/prov:scale-110">
                        </a>
                    `).join('')}
                </div>
            </div>
        `;
    }

    return `
        <div class="pt-8 border-t border-white/5">
            <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-6">Where to Watch</h4>
            ${renderGroup('Stream', wp.flatrate)}
            ${renderGroup('Rent', wp.rent)}
            ${renderGroup('Buy', wp.buy)}
            <a href="${escapeHtml(watchLink)}" target="_blank" rel="noopener"
               class="inline-flex items-center gap-2 mt-2 px-4 py-2 border border-accent-gold/30 text-accent-gold text-[9px] uppercase tracking-[0.2em] font-bold hover:bg-accent-gold/10 transition-all duration-300 rounded-full">
                <i data-lucide="external-link" class="w-3 h-3"></i>
                View All Options
            </a>
            <p class="text-[8px] text-cream/10 mt-4 tracking-wider">Powered by JustWatch</p>
        </div>
    `;
}

// ===== SHARED MODAL CONTENT =====

function renderModalContent(movie) {
    const oracleScore = calculateOracleScore(movie);
    const posterUrl = movie.poster_url || 'https://via.placeholder.com/300x450/0f172a/666?text=No+Poster';
    const backdropUrl = movie.backdrop_url || posterUrl;

    return `
        <div class="relative">
            <div class="h-80 sm:h-[30rem] relative overflow-hidden">
                <img src="${backdropUrl}" class="w-full h-full object-cover opacity-20 scale-105 blur-sm">
                <div class="absolute inset-0 bg-gradient-to-t from-[#0a0a0c] via-transparent to-transparent"></div>
            </div>
            <div class="px-8 sm:px-16 pb-20 -mt-60 relative">
                <div class="flex flex-col md:flex-row gap-12 items-end">
                    <img src="${posterUrl}" class="w-56 sm:w-80 shadow-[0_40px_80px_rgba(0,0,0,0.8)] border border-white/5 shrink-0">
                    <div class="flex-1 pb-4">
                        ${movie.performance ? `<div class="inline-block border border-accent-gold/40 text-accent-gold text-[9px] uppercase tracking-[0.3em] px-3 py-1 mb-6">${movie.performance}</div>` : ''}
                        <h2 class="text-5xl sm:text-8xl font-bold text-cream mb-6 tracking-tight leading-none">${escapeHtml(movie.title)}</h2>
                        <div class="flex flex-wrap gap-6 text-[10px] uppercase tracking-[0.2em] font-bold text-cream/40 items-center">
                            <span>${movie.year || 'N/A'}</span><span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span>${movie.runtime || '?'} min</span><span class="w-1 h-1 bg-white/10 rounded-full"></span>
                            <span class="text-accent-gold italic serif normal-case tracking-normal text-sm">${escapeHtml(movie.genres || 'N/A')}</span>
                        </div>
                    </div>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-16 mt-16">
                    <div class="lg:col-span-2 space-y-12">
                        <div><h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-6">The Synopsis</h4><p class="text-2xl text-cream/80 leading-relaxed serif italic">${escapeHtml(movie.overview)}</p></div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-12 pt-8 border-t border-white/5">
                            <div><h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Director</h4><p class="text-xl text-cream font-medium">${renderPeopleLinks(movie.director_links, movie.director)}</p></div>
                            <div><h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-4">Principals</h4><p class="text-xl text-cream font-medium">${renderPeopleLinks(movie.actor_links, movie.actors)}</p></div>
                        </div>
                    </div>
                    <div class="space-y-10">
                        <div class="border-l border-white/5 pl-8 py-2">
                             <h4 class="text-[9px] font-bold text-cream/20 uppercase tracking-[0.3em] mb-8">Production Analysis</h4>
                             <div class="space-y-6">
                                ${buildDetailRow('Expenditure', movie.budget)}
                                ${buildDetailRow('Market Yield', movie.revenue)}
                                ${movie.roi && movie.roi !== 'N/A' ? `<div class="pt-6 mt-6 border-t border-white/5"><p class="text-[9px] font-bold text-accent-gold uppercase tracking-[0.3em] mb-2">Yield Multiple</p><p class="text-4xl font-bold text-cream serif">${movie.roi}</p></div>` : ''}
                             </div>
                        </div>
                        <div class="flex gap-4 border-t border-white/5 pt-10">
                             ${buildRatingBox('Oracle', oracleScore, true)}
                             ${buildRatingBox('IMDb', movie.imdb_rating)}
                             ${buildRatingBox('RT', movie.rotten_tomatoes)}
                             ${buildRatingBox('Meta', movie.metascore)}
                        </div>
                        ${renderWatchProviders(movie)}
                    </div>
                </div>
            </div>
        </div>
    `;
}
