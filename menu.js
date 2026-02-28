// menu.js

const sidebarHTML = `
<aside id="sidebar"
class="fixed left-0 top-0 h-full w-64 bg-white border-r border-slate-200 z-50 flex flex-col justify-between transition-transform -translate-x-full md:translate-x-0">

    <!-- Parte superior -->
    <div>
        <div class="p-6 border-b border-slate-100">
            <h2 class="text-xl font-bold text-indigo-600 flex items-center gap-2">
                <i class="fas fa-compact-disc"></i> Somax Studios
            </h2>
            <p class="text-[11px] text-slate-500 mt-2 uppercase tracking-wide">
                Acervo Musical Digital
            </p>
        </div>

        <nav class="mt-4">
            <a href="index.html" class="nav-link flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors hover:bg-slate-50">
                <i class="fas fa-home w-5"></i> Dashboard
            </a>
            <a href="tapes.html" class="nav-link flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors hover:bg-slate-50">
                <i class="fas fa-tape w-5"></i> Tapes
            </a>
            <a href="musicas.html" class="nav-link flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors hover:bg-slate-50">
                <i class="fas fa-music w-5"></i> Músicas
            </a>
            <a href="artistas.html" class="nav-link flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors hover:bg-slate-50">
                <i class="fas fa-microphone w-5"></i> Artistas
            </a>
            <a href="gravadoras.html" class="nav-link flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors hover:bg-slate-50">
                <i class="fas fa-building w-5"></i> Gravadoras
            </a>
        </nav>
    </div>

    <!-- Parte inferior / Créditos -->
    <div class="p-6 border-t border-slate-100 bg-slate-50">
        <p class="text-[10px] text-slate-500 uppercase font-semibold tracking-wide">
            Acervo Musical Somax
        </p>
        <p class="text-[10px] text-slate-400 mt-1 leading-relaxed">
            Sistema interno de gestão de tapes, faixas e artistas.
        </p>
        <p class="text-[10px] text-slate-400 mt-3">
            © 2026 Somax Studios
        </p>
    </div>

</aside>
`;

const headerHTML = `
<header class="bg-white border-b border-slate-200 px-8 py-4 flex justify-between items-center sticky top-0 z-40">
    
    <button id="menuMobile" class="md:hidden text-slate-600 text-xl">
        <i class="fas fa-bars"></i>
    </button>

    <!-- Texto institucional -->
    <div class="text-sm font-semibold text-slate-600 uppercase tracking-wide hidden sm:block">
        Acervo Musical Somax Studios
    </div>

    <div class="text-[11px] text-slate-400 uppercase tracking-wider">
        Gestão de Catálogo
    </div>

</header>
`;

// Injeta o HTML ao carregar
document.addEventListener("DOMContentLoaded", () => {

    document.body.insertAdjacentHTML('afterbegin', sidebarHTML);
    document.getElementById('header-container').innerHTML = headerHTML;

    // Menu mobile
    document.getElementById('menuMobile').addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('-translate-x-full');
    });

    // Link ativo
    const currentPage = window.location.pathname.split("/").pop() || "index.html";

    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === currentPage) {
            link.classList.add('bg-slate-50', 'text-indigo-600', 'border-r-4', 'border-indigo-600');
        } else {
            link.classList.add('text-slate-600');
        }
    });

});