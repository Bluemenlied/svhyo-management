// Theme management
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    // Update theme setting in database via API
    fetch('/api/settings/theme', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ theme: theme })
    }).catch(err => console.error('Error saving theme:', err));
}

function getTheme() {
    return localStorage.getItem('theme') || 'light';
}

function toggleTheme() {
    const currentTheme = getTheme();
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
}

// Initialize theme
document.addEventListener('DOMContentLoaded', function () {
    const theme = getTheme();
    setTheme(theme);

    // Add theme toggle button if not exists
    if (!document.getElementById('themeToggle')) {
        const navbar = document.querySelector('.navbar-nav');
        if (navbar) {
            const li = document.createElement('li');
            li.className = 'nav-item';
            li.innerHTML = `
                <button id="themeToggle" class="btn btn-link nav-link">
                    <i class="bi bi-${theme === 'light' ? 'moon' : 'sun'}"></i>
                </button>
            `;
            navbar.appendChild(li);

            document.getElementById('themeToggle').addEventListener('click', toggleTheme);
        }
    }
});