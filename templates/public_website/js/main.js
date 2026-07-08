// Global data storage
let siteData = { settings: {}, officers: [], events: [], accomplishments: [] };

async function loadData() {
    try {
        const [settings, officers, events, accomplishments] = await Promise.all([
            fetch('data/settings.json').then(r => r.json()).catch(() => ({})),
            fetch('data/officers.json').then(r => r.json()).catch(() => []),
            fetch('data/events.json').then(r => r.json()).catch(() => []),
            fetch('data/accomplishments.json').then(r => r.json()).catch(() => [])
        ]);
        siteData = { settings, officers, events, accomplishments };
        return siteData;
    } catch (error) {
        console.error('Error loading data:', error);
        return siteData;
    }
}

function formatDate(dateString) {
    if (!dateString) return 'TBA';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch { return dateString; }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function updateFooterContact(settings) {
    const contactInfo = document.getElementById('contactInfo');
    const socialLinks = document.getElementById('socialLinks');
    if (contactInfo) {
        let html = '';
        if (settings.contact_email) html += `<li><i class="bi bi-envelope me-2"></i> ${escapeHtml(settings.contact_email)}</li>`;
        if (settings.contact_phone) html += `<li><i class="bi bi-telephone me-2"></i> ${escapeHtml(settings.contact_phone)}</li>`;
        if (settings.contact_address) html += `<li><i class="bi bi-geo-alt me-2"></i> ${escapeHtml(settings.contact_address)}</li>`;
        contactInfo.innerHTML = html || '<li>No contact info available</li>';
    }
    if (socialLinks) {
        let html = '';
        if (settings.social_facebook) html += `<a href="${escapeHtml(settings.social_facebook)}" target="_blank"><i class="bi bi-facebook"></i></a>`;
        if (settings.social_twitter) html += `<a href="${escapeHtml(settings.social_twitter)}" target="_blank"><i class="bi bi-twitter-x"></i></a>`;
        if (settings.social_instagram) html += `<a href="${escapeHtml(settings.social_instagram)}" target="_blank"><i class="bi bi-instagram"></i></a>`;
        socialLinks.innerHTML = html;
    }
}

function initNavbar() {
    window.addEventListener('scroll', function() {
        const navbar = document.querySelector('.navbar');
        const scrollTop = document.getElementById('scrollTop');
        if (window.scrollY > 50) {
            navbar?.classList.add('scrolled');
            scrollTop?.classList.add('show');
        } else {
            navbar?.classList.remove('scrolled');
            scrollTop?.classList.remove('show');
        }
    });
    const scrollTopBtn = document.getElementById('scrollTop');
    if (scrollTopBtn) {
        scrollTopBtn.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
}

function initScrollAnimation() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
    document.querySelectorAll('.animate-on-scroll').forEach(el => observer.observe(el));
}
