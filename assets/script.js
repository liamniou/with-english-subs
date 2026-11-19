// Global variables
let allFilms = [];
let filteredFilms = [];
let cinemas = new Set();
let genres = new Set();

// Simplified DateTime parsing using normalized data
function parseDateTime(showtime) {
    // Use normalized_datetime if available (preferred)
    if (showtime.normalized_datetime) {
        try {
            return new Date(showtime.normalized_datetime);
        } catch (e) {
            console.warn('Could not parse normalized_datetime:', showtime.normalized_datetime, e);
        }
    }
    
    // Fallback to original datetime field with intelligent date parsing
    if (showtime.datetime) {
        try {
            // Parse various datetime formats
            let dateStr = showtime.datetime.trim();
            
            // Try to detect format:  DD.MM HH:MM or DD.MM. YYYY HH:MM
            const dateTimeRegex = /^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
            const match = dateStr.match(dateTimeRegex);
            
            if (match) {
                const day = parseInt(match[1], 10);
                const month = parseInt(match[2], 10);
                let year = match[3] ? parseInt(match[3], 10) : null;
                const hours = parseInt(match[4], 10);
                const minutes = parseInt(match[5], 10);
                
                // If no year provided, intelligently determine it
                if (!year) {
                    const now = new Date();
                    const currentYear = now.getFullYear();
                    const currentMonth = now.getMonth() + 1;
                    const currentDay = now.getDate();
                    
                    // If the month/day is in the past this year, use next year
                    if (month < currentMonth || (month === currentMonth && day < currentDay)) {
                        year = currentYear + 1;
                    } else {
                        year = currentYear;
                    }
                }
                
                return new Date(year, month - 1, day, hours, minutes, 0);
            }
            
            // Fallback to native Date parsing
            return new Date(dateStr);
        } catch (e) {
            console.warn('Could not parse datetime:', showtime.datetime, e);
        }
    }
    
    return null;
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
    // Use normalized data if available (much simpler!)
    if (showtime.normalized_datetime && showtime.normalized_date && showtime.normalized_time) {
        const parsedDate = new Date(showtime.normalized_datetime);
        
        // Validate the normalized date
        if (!isNaN(parsedDate.getTime())) {
            return {
                display: showtime.normalized_time,
                date: showtime.normalized_date,
                time: showtime.normalized_time,
                fullDate: parsedDate
            };
        }
    }
    
    // Fallback to legacy parsing if normalized data is not available
    const parsedDate = parseDateTime(showtime);
    
    if (!parsedDate || isNaN(parsedDate.getTime())) {
        // Final fallback to original display
        return {
            display: showtime.display_text || showtime.datetime || 'TBA',
            date: '',
            time: '',
            fullDate: null
        };
    }
    
    const now = new Date();
    
    // Format time
    const timeOptions = { hour: '2-digit', minute: '2-digit', hour12: false };
    const timeStr = parsedDate.toLocaleTimeString('en-GB', timeOptions);
    
    // Format date - always use numeric format
    const day = String(parsedDate.getDate()).padStart(2, '0');
    const month = String(parsedDate.getMonth() + 1).padStart(2, '0');
    let dateStr = `${day}.${month}`;
    
    // Add year if not current year
    if (parsedDate.getFullYear() !== now.getFullYear()) {
        dateStr += `.${parsedDate.getFullYear()}`;
    }
    
    return {
        display: timeStr,
        date: dateStr,
        time: timeStr,
        fullDate: parsedDate
    };
}

// Generate Google Calendar URL for a film showtime
function createGoogleCalendarUrl(film, showtime, formattedDateTime) {
    if (!formattedDateTime.fullDate) {
        return null;
    }
    
    const startDate = new Date(formattedDateTime.fullDate);
    
    // Check if the date is valid
    if (isNaN(startDate.getTime())) {
        console.warn('Invalid date for calendar URL:', formattedDateTime.fullDate);
        return null;
    }
    
    // Assume 2-hour duration for films (default)
    const endDate = new Date(startDate.getTime() + (2 * 60 * 60 * 1000));
    
    // Format dates for Google Calendar (YYYYMMDDTHHMMSSZ)
    const formatGoogleDate = (date) => {
        try {
            return date.toISOString().replace(/[-:.]/g, '').replace(/000Z$/, 'Z');
        } catch (error) {
            console.warn('Error formatting date for Google Calendar:', date, error);
            return null;
        }
    };
    
    const startDateFormatted = formatGoogleDate(startDate);
    const endDateFormatted = formatGoogleDate(endDate);
    
    // If date formatting failed, return null
    if (!startDateFormatted || !endDateFormatted) {
        return null;
    }
    
    // Don't use encodeURIComponent here since URLSearchParams will handle encoding
    const title = `🍿 ${film.tmdb?.title || film.title}`;
    const cinemaName = cleanCinemaName(showtime.source_cinema || film.data_source || 'Stockholm Cinema');
    const details = [
        `Film: ${film.tmdb?.title || film.title}`,
        film.tmdb?.overview ? `Description: ${film.tmdb.overview}` : '',
        film.tmdb?.directors?.length > 0 ? `Director: ${film.tmdb.directors.join(', ')}` : '',
        film.tmdb?.genres?.length > 0 ? `Genres: ${film.tmdb.genres.join(', ')}` : '',
        film.tmdb?.rating ? `Rating: ⭐ ${film.tmdb.rating}/10` : '',
        '',
        `Cinema: ${cinemaName}`,
        `Ticket URL: ${getShowtimeUrl(film, showtime)}`
    ].filter(line => line.trim()).join('\n');
    
    const location = cinemaName;
    
    const baseUrl = 'https://calendar.google.com/calendar/render';
    const params = new URLSearchParams({
        action: 'TEMPLATE',
        text: title,
        dates: `${startDateFormatted}/${endDateFormatted}`,
        details: details,
        location: location
    });
    
    return `${baseUrl}?${params.toString()}`;
}

// Helper function to clean cinema names (remove "Bio" prefix)
function cleanCinemaName(cinemaName) {
    if (!cinemaName) return '';
    
    // Remove "Bio " prefix (case insensitive)
    return cinemaName.replace(/^Bio\s+/i, '').trim();
}

// Helper function to get the appropriate URL for a showtime
function getShowtimeUrl(film, showtime) {
    // Get the appropriate URL for this showtime's cinema
    let showtimeUrl = film.url; // default fallback
    const cinemaInfo = showtime.source_cinema || showtime.source_cinemas?.[0] || '';
    
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
    
    return showtimeUrl;
}

// DOM elements
const filmsGrid = document.getElementById('films-grid');
const loading = document.getElementById('loading');
const noResults = document.getElementById('no-results');
const resultsCount = document.getElementById('results-count');
const filtersForm = document.getElementById('filters-form');

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
        file: './data/cinemateket_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Bio Rio Stockholm',
        file: './data/biorio_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Bio Fågel Blå Stockholm',
        file: './data/fagelbla_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Zita Folkets Bio Stockholm',
        file: './data/zita_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Klarabiografen',
        file: './data/klarabiografen_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Capitol',
        file: './data/capitolbio_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Bio Aspen',
        file: './data/bioaspen_films_with_english_subs.json',
        fallback: null
    },
    {
        name: 'Bio Bristol',
        file: './data/biobristol_films_with_english_subs.json',
        fallback: null
    },
    {
        // Each film carries its own data_source (cinema name) from the scraper
        name: 'bio.se',
        file: './data/biose_films_with_english_subs.json',
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
                        film.data_source = film.data_source || source.name;
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
        
        // Filter out past showtimes and films left with no upcoming showings
        const now = new Date();
        // Treat anything before the start of today as past, so films showing later today still appear
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        allFilms = allFilms
            .map(film => {
                if (!Array.isArray(film.showtimes)) return film;
                const upcoming = film.showtimes.filter(st => {
                    const dt = parseDateTime(st);
                    if (!dt || isNaN(dt.getTime())) return true; // keep unparseable showtimes
                    return dt >= startOfToday;
                });
                return { ...film, showtimes: upcoming };
            })
            .filter(film => Array.isArray(film.showtimes) && film.showtimes.length > 0);
        
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
        loading.textContent = 'Error loading films. Please try again later.';
    }
}



// Setup event listeners for filters
function setupEventListeners() {
    // Filtering is live, so pressing Enter in the search field must not reload the page
    filtersForm.addEventListener('submit', (e) => e.preventDefault());
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
    resultsCount.textContent = films.length === allFilms.length
        ? ''
        : `${films.length} of ${allFilms.length} films`;

    if (films.length === 0) {
        filmsGrid.hidden = true;
        noResults.hidden = false;
        return;
    }
    
    filmsGrid.hidden = false;
    noResults.hidden = true;
    
    // Sort films by their earliest showtime
    const sortedFilms = [...films].sort((a, b) => {
        const dateA = getEarliestShowtime(a);
        const dateB = getEarliestShowtime(b);
        return dateA - dateB;
    });
    
    filmsGrid.innerHTML = sortedFilms.map((film, index) => createFilmCard(film, index)).join('');
}

const VISIBLE_SHOWTIMES = 4;

function escapeAttr(value) {
    return String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function icon(name) {
    return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

function createShowtimeItem(film, title, showtime) {
    const formattedDateTime = formatShowtime(showtime);
    const when = `${formattedDateTime.date} ${formattedDateTime.display}`.trim();
    const cinema = cleanCinemaName(showtime.source_cinema || showtime.source_cinemas?.[0] || '');
    const showtimeUrl = getShowtimeUrl(film, showtime);
    const calendarUrl = createGoogleCalendarUrl(film, showtime, formattedDateTime);

    return `
        <li class="showtime">
            <a href="${showtimeUrl}" target="_blank" rel="noopener" class="showtime-link">
                <span class="showtime-time">${when}</span>
                ${cinema ? `<span class="cinema-name">${cinema}</span>` : ''}
            </a>
            ${calendarUrl ? `
                <a href="${calendarUrl}" target="_blank" rel="noopener" class="calendar-button"
                   title="Add to Google Calendar"
                   aria-label="${escapeAttr(`Add ${title}, ${when}${cinema ? ` at ${cinema}` : ''}, to Google Calendar`)}">
                    ${icon('calendar-plus')}
                </a>
            ` : ''}
        </li>`;
}

// Create HTML for a film card
function createFilmCard(film, index = 0) {
    const tmdb = film.tmdb || {};
    const title = tmdb.title || film.title || 'Untitled';
    const overview = tmdb.overview || film.description || extractOverviewFromDetails(film.original_details) || 'No description available.';
    const rating = tmdb.rating ? tmdb.rating.toFixed(1) : null;
    const genres = tmdb.genres?.slice(0, 2) || [];
    const year = tmdb.release_date ? new Date(tmdb.release_date).getFullYear() : '';
    const posterUrl = tmdb.poster_url || film.poster_url || '';
    const directors = tmdb.directors?.slice(0, 2) || [];
    const filmUrl = film.url || film.urls?.[0] || '';
    const sources = film.data_sources?.length > 1 ? film.data_sources : (film.data_source ? [film.data_source] : []);
    const showtimes = getSortedShowtimes(film.showtimes);
    const visibleShowtimes = showtimes.slice(0, VISIBLE_SHOWTIMES);
    const extraShowtimes = showtimes.slice(VISIBLE_SHOWTIMES);
    // The first poster is the likely LCP element; the rest can load lazily
    const posterLoading = index === 0 ? 'fetchpriority="high"' : 'loading="lazy"';

    return `
        <article class="film-card">
            ${posterUrl
                ? `<img class="film-poster" src="${posterUrl}" alt="" width="500" height="750" ${posterLoading} decoding="async">`
                : `<div class="film-poster placeholder">${icon('film')}</div>`
            }
            ${rating ? `
                <span class="film-rating"><span aria-hidden="true">★</span><span class="visually-hidden">Rating</span> ${rating}</span>
            ` : ''}
            <h2 class="film-title">
                ${filmUrl ? `<a href="${filmUrl}" target="_blank" rel="noopener">${title}</a>` : title}
            </h2>
            <p class="film-overview">${overview}</p>
            <ul class="film-meta">
                ${year ? `<li class="meta-item year">${year}</li>` : ''}
                ${genres.map(genre => `<li class="meta-item genre">${genre}</li>`).join('')}
                ${directors.length > 0 ? `<li class="meta-item director"><span class="visually-hidden">Directed by </span>${directors.join(', ')}</li>` : ''}
                ${sources.map(source => `<li class="meta-item source">${source}</li>`).join('')}
            </ul>
            <footer class="film-showtimes">
                ${showtimes.length > 0 ? `
                    <h3 class="showtimes-title">Showtimes</h3>
                    <ul class="showtime-list">
                        ${visibleShowtimes.map(showtime => createShowtimeItem(film, title, showtime)).join('')}
                    </ul>
                    ${extraShowtimes.length > 0 ? `
                        <details class="more-showtimes">
                            <summary>${extraShowtimes.length} more showtime${extraShowtimes.length === 1 ? '' : 's'}</summary>
                            <ul class="showtime-list">
                                ${extraShowtimes.map(showtime => createShowtimeItem(film, title, showtime)).join('')}
                            </ul>
                        </details>
                    ` : ''}
                ` : ''}
            </footer>
        </article>
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

// Hide the sticky filter bar while scrolling down where CSS scroll-state queries aren't supported
if (!CSS.supports('container-type', 'scroll-state')) {
    const header = document.querySelector('.site-header');
    const bar = document.querySelector('.top-bar');
    let lastY = scrollY;
    addEventListener('scroll', () => {
        // Clamp so rubber-band overscroll at the top or bottom doesn't flip the scroll direction
        const y = Math.max(0, Math.min(scrollY, document.documentElement.scrollHeight - innerHeight));
        if (y === lastY) return;
        // Hide only once the bar is stuck to the top, so it never slides over the page header
        bar?.classList.toggle('is-hidden', y > lastY && y > header.offsetHeight + bar.offsetHeight);
        lastY = y;
    }, { passive: true });
}
