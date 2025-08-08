// Global variables
let allFilms = [];
let filteredFilms = [];
let cinemas = new Set();
let genres = new Set();

// DateTime parsing and formatting utilities
function parseDateTime(showtime) {
    if (!showtime.datetime) return null;
    
    try {
        // Check if it's already an ISO datetime string (Bio Rio/Bio Fågel Blå)
        if (showtime.datetime.includes('T') && (showtime.datetime.includes('Z') || showtime.datetime.includes('+'))) {
            return new Date(showtime.datetime);
        }
        
        // Handle Cinemateket format "Sun 24/8 at 16:00"
        if (showtime.datetime.includes(' at ')) {
            const parts = showtime.datetime.split(' at ');
            if (parts.length === 2) {
                const datePart = parts[0]; // e.g., "Sun 24/8"
                const timePart = parts[1]; // e.g., "16:00"
                
                // Extract day and month from "Sun 24/8"
                const dateMatch = datePart.match(/(\d+)\/(\d+)/);
                if (dateMatch) {
                    const day = parseInt(dateMatch[1]);
                    const month = parseInt(dateMatch[2]);
                    const year = new Date().getFullYear(); // Use current year as default
                    
                    // Parse time "16:00"
                    const timeMatch = timePart.match(/(\d+):(\d+)/);
                    if (timeMatch) {
                        const hours = parseInt(timeMatch[1]);
                        const minutes = parseInt(timeMatch[2]);
                        
                        return new Date(year, month - 1, day, hours, minutes);
                    }
                }
            }
        }
        
        // Fallback: try to parse as standard date
        return new Date(showtime.datetime);
    } catch (e) {
        console.warn('Could not parse datetime:', showtime.datetime, e);
        return null;
    }
}

function getSortedShowtimes(showtimes) {
    if (!showtimes || !Array.isArray(showtimes)) return [];
    
    return [...showtimes].sort((a, b) => {
        const dateA = parseDateTime(a);
        const dateB = parseDateTime(b);
        
        // If either date couldn't be parsed, keep original order
        if (!dateA && !dateB) return 0;
        if (!dateA) return 1;
        if (!dateB) return -1;
        
        return dateA - dateB;
    });
}

function formatShowtime(showtime) {
    const parsedDate = parseDateTime(showtime);
    
    if (!parsedDate) {
        // Fallback to original display if parsing fails
        return {
            display: showtime.display_text || showtime.datetime || 'TBA',
            date: '',
            time: ''
        };
    }
    
    const now = new Date();
    const isToday = parsedDate.toDateString() === now.toDateString();
    const isTomorrow = parsedDate.toDateString() === new Date(now.getTime() + 24 * 60 * 60 * 1000).toDateString();
    
    // Format time
    const timeOptions = { hour: '2-digit', minute: '2-digit', hour12: false };
    const timeStr = parsedDate.toLocaleTimeString('en-GB', timeOptions);
    
    // Format date
    let dateStr;
    if (isToday) {
        dateStr = 'Today';
    } else if (isTomorrow) {
        dateStr = 'Tomorrow';
    } else {
        const dateOptions = { 
            month: 'short', 
            day: 'numeric'
        };
        dateStr = parsedDate.toLocaleDateString('en-GB', dateOptions);
        
        // Add year if not current year
        if (parsedDate.getFullYear() !== now.getFullYear()) {
            dateStr += ` ${parsedDate.getFullYear()}`;
        }
    }
    
    return {
        display: timeStr,
        date: dateStr,
        time: timeStr,
        fullDate: parsedDate
    };
}

// DOM elements
const filmsGrid = document.getElementById('films-grid');
const loading = document.getElementById('loading');
const noResults = document.getElementById('no-results');

const searchInput = document.getElementById('search-input');
const cinemaFilter = document.getElementById('cinema-filter');
const genreFilter = document.getElementById('genre-filter');
const totalFilmsEl = document.getElementById('total-films');
const totalCinemasEl = document.getElementById('total-cinemas');
const totalShowtimesEl = document.getElementById('total-showtimes');

// Initialize the app
document.addEventListener('DOMContentLoaded', async () => {
    await loadFilms();
    setupEventListeners();
    displayFilms(allFilms);
    updateStats();
    populateFilters();
});

// Configuration for data sources
const DATA_SOURCES = [
    {
        name: 'Cinemateket Stockholm',
        file: './cinemateket_films_with_english_subs.json',
        fallback: './films_with_english_subs.json'
    },
    {
        name: 'Bio Rio Stockholm',
        file: './biorio_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Bio Fågel Blå Stockholm',
        file: './fagelbla_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Zita Folkets Bio Stockholm',
        file: './zita_films_with_english_subs.json',
        fallback: null
    }
];

// Load films from multiple JSON files
async function loadFilms() {
    try {
        let loadedSources = 0;
        let totalFilms = 0;
        allFilms = [];
        
        console.log('🎬 Loading films from multiple sources...');
        
        for (const source of DATA_SOURCES) {
            try {
                console.log(`📋 Loading from ${source.name}...`);
                
                let response = await fetch(source.file);
                
                // Try fallback if main file fails
                if (!response.ok && source.fallback) {
                    console.log(`⚠️  Primary file failed, trying fallback for ${source.name}...`);
                    response = await fetch(source.fallback);
                }
                
                if (response.ok) {
                    const films = await response.json();
                    
                    // Add source information to each film
                    films.forEach(film => {
                        film.data_source = source.name;
                        film.source_file = response.url.split('/').pop();
                    });
                    
                    allFilms.push(...films);
                    loadedSources++;
                    totalFilms += films.length;
                    
                    console.log(`✅ Loaded ${films.length} films from ${source.name}`);
                } else {
                    console.log(`❌ Failed to load from ${source.name}`);
                }
                
            } catch (error) {
                console.error(`Error loading ${source.name}:`, error);
            }
        }
        
        // Films are already merged by static_generator.py
        
        filteredFilms = [...allFilms];
        
        // Extract unique cinemas and genres
        allFilms.forEach(film => {
            film.cinemas?.forEach(cinema => {
                if (typeof cinema === 'string') {
                    cinemas.add(cinema);
                } else if (cinema?.name) {
                    cinemas.add(cinema.name);
                }
            });
            film.tmdb?.genres?.forEach(genre => genres.add(genre));
        });
        
        console.log(`🎉 Successfully loaded ${allFilms.length} films from ${loadedSources} sources`);
        
        if (allFilms.length === 0) {
            throw new Error('No films data found from any source');
        }
        
        loading.style.display = 'none';
    } catch (error) {
        console.error('Error loading films:', error);
        loading.innerHTML = `
            <i class="fas fa-exclamation-triangle"></i>
            <span>Error loading films. Please try again later.</span>
        `;
    }
}



// Setup event listeners for filters
function setupEventListeners() {
    searchInput.addEventListener('input', debounce(filterFilms, 300));
    cinemaFilter.addEventListener('change', filterFilms);
    genreFilter.addEventListener('change', filterFilms);
}

// Debounce function for search input
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Filter films based on search and criteria
function filterFilms() {
    const searchTerm = searchInput.value.toLowerCase();
    const selectedCinema = cinemaFilter.value;
    const selectedGenre = genreFilter.value;
    
    filteredFilms = allFilms.filter(film => {
        // Search filter
        const searchMatch = !searchTerm || 
            film.title?.toLowerCase().includes(searchTerm) ||
            film.tmdb?.title?.toLowerCase().includes(searchTerm) ||
            film.tmdb?.overview?.toLowerCase().includes(searchTerm) ||
            film.tmdb?.directors?.some(dir => dir.toLowerCase().includes(searchTerm)) ||
            film.tmdb?.genres?.some(genre => genre.toLowerCase().includes(searchTerm));
        
        // Cinema filter
        const cinemaMatch = !selectedCinema || 
            film.cinemas?.some(cinema => {
                if (typeof cinema === 'string') {
                    return cinema === selectedCinema;
                } else if (cinema?.name) {
                    return cinema.name === selectedCinema;
                }
                return false;
            });
        
        // Genre filter
        const genreMatch = !selectedGenre || 
            film.tmdb?.genres?.includes(selectedGenre);
        
        return searchMatch && cinemaMatch && genreMatch;
    });
    
    displayFilms(filteredFilms);
}

// Get the earliest showtime date for a film
function getEarliestShowtime(film) {
    if (!film.showtimes || film.showtimes.length === 0) {
        return new Date('2099-12-31'); // Far future date for films without showtimes
    }
    
    const sortedShowtimes = getSortedShowtimes(film.showtimes);
    const earliestShowtime = sortedShowtimes[0];
    const parsedDate = parseDateTime(earliestShowtime);
    
    return parsedDate || new Date('2099-12-31');
}

// Display films in the grid
function displayFilms(films) {
    if (films.length === 0) {
        filmsGrid.style.display = 'none';
        noResults.style.display = 'block';
        return;
    }
    
    filmsGrid.style.display = 'grid';
    noResults.style.display = 'none';
    
    // Sort films by their earliest showtime
    const sortedFilms = [...films].sort((a, b) => {
        const dateA = getEarliestShowtime(a);
        const dateB = getEarliestShowtime(b);
        return dateA - dateB;
    });
    
    filmsGrid.innerHTML = sortedFilms.map(film => createFilmCard(film)).join('');
}

// Create HTML for a film card
function createFilmCard(film) {
    const tmdb = film.tmdb || {};
    const fullTitle = tmdb.title || film.title || 'Untitled';
    const title = fullTitle.length > 20 ? fullTitle.substring(0, 20) + '...' : fullTitle;
    const overview = tmdb.overview || extractOverviewFromDetails(film.original_details) || 'No description available.';
    const rating = tmdb.rating ? tmdb.rating.toFixed(1) : null;
            const genres = tmdb.genres?.slice(0, 2) || [];
    const year = tmdb.release_date ? new Date(tmdb.release_date).getFullYear() : '';
    const runtime = tmdb.runtime ? `${tmdb.runtime} min` : '';
    const posterUrl = tmdb.poster_url || '';
    const directors = tmdb.directors?.slice(0, 2) || [];
    
    return `
        <div class="film-card">
            <div class="film-poster">
                ${posterUrl ? 
                    `<img src="${posterUrl}" alt="${title}" loading="lazy">` : 
                    `<div class="placeholder"><i class="fas fa-film"></i></div>`
                }
                ${rating ? `
                    <div class="film-rating">
                        <span class="star">★</span>
                        <span>${rating}</span>
                    </div>
                ` : ''}
            </div>
            <div class="film-content">
                <h3 class="film-title">${title}</h3>
                <p class="film-overview">${overview}</p>
                
                <div class="film-meta">
                    ${year ? `<span class="meta-item year">${year}</span>` : ''}
                    ${genres.map(genre => `<span class="meta-item genre">${genre}</span>`).join('')}
                    ${directors.length > 0 ? `<span class="meta-item">📽️ ${directors.join(', ')}</span>` : ''}
                    ${film.data_sources && film.data_sources.length > 1 ? 
                        film.data_sources.map(source => `<span class="meta-item source multi-cinema"> ${source}</span>`).join('') :
                        film.data_source ? `<span class="meta-item source"> ${film.data_source}</span>` : ''
                    }
                </div>
                
                ${film.showtimes?.length > 0 ? `
                    <div class="film-showtimes">
                        <div class="showtimes-title">
                            <i class="fas fa-clock"></i>
                            Showtimes
                        </div>
                        ${getSortedShowtimes(film.showtimes).slice(0, 5).map(showtime => {
                        const formattedDateTime = formatShowtime(showtime);
                        const cinemaInfo = showtime.source_cinema || showtime.source_cinemas?.[0] || '';
                        
                        // Get the appropriate URL for this showtime's cinema
                        let showtimeUrl = film.url; // default fallback
                        if (film.urls && film.data_sources && cinemaInfo) {
                            const cinemaIndex = film.data_sources.findIndex(source => 
                                source.toLowerCase().includes(cinemaInfo.toLowerCase()) ||
                                cinemaInfo.toLowerCase().includes(source.toLowerCase())
                            );
                            if (cinemaIndex >= 0 && film.urls[cinemaIndex]) {
                                showtimeUrl = film.urls[cinemaIndex];
                            }
                        } else if (showtime.source_url) {
                            showtimeUrl = showtime.source_url;
                        }
                        
                        return `
                        <a href="${showtimeUrl}" target="_blank" class="showtime-link">
                            <div class="showtime ${film.data_sources && film.data_sources.length > 1 ? 'multi-cinema' : ''}">
                                <div class="showtime-time">${formattedDateTime.date} ${formattedDateTime.display}${cinemaInfo ? ` <span class="cinema-name">${cinemaInfo}</span>` : ''}</div>
                                <div class="showtime-arrow">→</div>
                            </div>
                        </a>`;
                    }).join('')}
                    ${film.showtimes.length > 5 ? `<div class="more-showtimes">+${film.showtimes.length - 5} more showtimes...</div>` : ''}
                    </div>
                ` : ''}
                

            </div>
        </div>
    `;
}

// Extract overview from original details (fallback)
function extractOverviewFromDetails(details) {
    if (!details) return '';
    
    // Remove HTML tags and extra whitespace
    const cleanText = details.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
    
    // Get first meaningful paragraph (minimum 50 characters)
    const sentences = cleanText.split('. ');
    let overview = '';
    for (const sentence of sentences) {
        overview += sentence + '. ';
        if (overview.length > 100) break;
    }
    
    return overview.trim().substring(0, 200) + (overview.length > 200 ? '...' : '');
}

// Update statistics
function updateStats() {
    totalFilmsEl.textContent = allFilms.length;
    totalCinemasEl.textContent = cinemas.size;
    
    const totalShowtimes = allFilms.reduce((total, film) => {
        return total + (film.showtimes?.length || 0);
    }, 0);
    totalShowtimesEl.textContent = totalShowtimes;
}

// Populate filter dropdowns
function populateFilters() {
    // Populate cinema filter
    const sortedCinemas = Array.from(cinemas).sort();
    sortedCinemas.forEach(cinema => {
        const option = document.createElement('option');
        option.value = cinema;
        option.textContent = cinema;
        cinemaFilter.appendChild(option);
    });
    
    // Populate genre filter
    const sortedGenres = Array.from(genres).sort();
    sortedGenres.forEach(genre => {
        const option = document.createElement('option');
        option.value = genre;
        option.textContent = genre;
        genreFilter.appendChild(option);
    });
}

// Smooth scroll to films section
function scrollToFilms() {
    document.getElementById('films').scrollIntoView({
        behavior: 'smooth'
    });
}

// Add click handlers for navigation
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('.nav-links a');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            if (link.getAttribute('href').startsWith('#')) {
                e.preventDefault();
                const targetId = link.getAttribute('href');
                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    targetElement.scrollIntoView({
                        behavior: 'smooth'
                    });
                }
            }
        });
    });
});

// Add loading states for images
document.addEventListener('DOMContentLoaded', () => {
    // Add intersection observer for lazy loading optimization
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        observer.unobserve(img);
                    }
                }
            });
        });

        // Observe all images with data-src
        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }
});