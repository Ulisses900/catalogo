// Sidebar
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    sidebar.classList.toggle('collapsed');
}

// Submenus
function toggleSubmenu(id) {
    const submenu = document.getElementById(`${id}-submenu`);
    const arrow = document.getElementById(`${id}-arrow`);
    submenu.classList.toggle('active');
    arrow.classList.toggle('fa-chevron-down');
    arrow.classList.toggle('fa-chevron-up');
}

// Funções para abrir e fechar modals
function openModal(type, title, data = null) {
    // Implementação genérica para abrir modals
}

function closeModal() {
    document.getElementById('modal-container').classList.add('hidden');
    document.getElementById('modal-container').classList.remove('flex');
}

// Funções para carregar dados em cada página
function loadArtistas(searchTerm = '') {
    // Implementação para carregar artistas
}

function loadEtiquetas() {
    // Implementação similar para etiquetas
}

function loadGravadoras() {
    // Implementação similar para gravadoras
}

function loadTapes() {
    // Implementação similar para tapes
}

// Event Listeners para busca
document.addEventListener('DOMContentLoaded', function() {
    // Configurar busca para cada página
    if (document.getElementById('search-artista')) {
        document.getElementById('search-artista').addEventListener('input', function(e) {
            loadArtistas(e.target.value);
        });
    }
    
    // Configurações semelhantes para outras páginas...
});

// CRUD Operations
function saveArtista() {
    // Implementação para salvar artista
}

function deleteArtista(id) {
    // Implementação para excluir artista
}

// Funções semelhantes para outros modelos