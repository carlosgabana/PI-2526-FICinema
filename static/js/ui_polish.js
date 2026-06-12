(function () {
    "use strict";

    const OVERLAY_CLASS = "ficinema-loading-overlay";
    const VISIBLE_CLASS = "is-visible";
    const BODY_LOADING_CLASS = "ficinema-is-loading";

    let loaderVisible = false;

    function crearSkeletonCard() {
        return `
            <div class="ficinema-skeleton-card">
                <div class="skeleton-block skeleton-poster"></div>
                <div class="skeleton-lines">
                    <div class="skeleton-block skeleton-line-lg"></div>
                    <div class="skeleton-block skeleton-line-md"></div>
                    <div class="skeleton-block skeleton-line-sm"></div>
                    <div class="skeleton-block skeleton-line-sm"></div>
                    <div class="skeleton-block skeleton-button"></div>
                </div>
            </div>
        `;
    }

    function crearOverlay() {
        let overlay = document.querySelector(`.${OVERLAY_CLASS}`);

        if (overlay) {
            return overlay;
        }

        overlay = document.createElement("div");
        overlay.className = OVERLAY_CLASS;
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML = `
            <div class="ficinema-loading-panel" role="status" aria-live="polite">
                <p class="ficinema-loading-title">Cargando FICinema...</p>
                <p class="ficinema-loading-subtitle">Preparando cartelera, sesiones y datos de la película.</p>
                <div class="ficinema-skeleton-grid">
                    ${crearSkeletonCard()}
                    ${crearSkeletonCard()}
                    ${crearSkeletonCard()}
                    ${crearSkeletonCard()}
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        return overlay;
    }

    function mostrarCarga() {
        const overlay = crearOverlay();

        loaderVisible = true;
        document.body.classList.add(BODY_LOADING_CLASS);
        overlay.classList.add(VISIBLE_CLASS);
    }

    function ocultarCarga() {
        const overlay = document.querySelector(`.${OVERLAY_CLASS}`);

        loaderVisible = false;

        if (overlay) {
            overlay.classList.remove(VISIBLE_CLASS);
        }

        document.body.classList.remove(BODY_LOADING_CLASS);
    }

    function esRutaDeDescargaOArchivo(ruta) {
        const valor = (ruta || "").trim().toLowerCase();

        return (
            valor.includes("/exportar/") ||
            valor.includes("/pdf/") ||
            valor.includes("/qr/") ||
            valor.endsWith(".csv") ||
            valor.endsWith(".pdf") ||
            valor.endsWith(".png") ||
            valor.endsWith(".jpg") ||
            valor.endsWith(".jpeg") ||
            valor.endsWith(".webp")
        );
    }

    function esDescargaOArchivo(link) {
        if (!link) {
            return false;
        }

        return (
            link.dataset.noLoader === "true" ||
            link.hasAttribute("download") ||
            esRutaDeDescargaOArchivo(link.getAttribute("href"))
        );
    }

    function esFormularioDeDescargaOArchivo(form) {
        if (!form) {
            return false;
        }

        return (
            form.dataset.noLoader === "true" ||
            form.hasAttribute("data-no-loading") ||
            form.hasAttribute("download") ||
            esRutaDeDescargaOArchivo(form.getAttribute("action"))
        );
    }

    function esNavegacionInternaValida(link, event) {
        if (!link || !link.href || event.defaultPrevented) {
            return false;
        }

        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) {
            return false;
        }

        if (link.target && link.target !== "_self") {
            return false;
        }

        if (esDescargaOArchivo(link)) {
            return false;
        }

        let url;

        try {
            url = new URL(link.href, window.location.href);
        } catch (_error) {
            return false;
        }

        if (url.origin !== window.location.origin) {
            return false;
        }

        if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) {
            return false;
        }

        return true;
    }

    function prepararMensajesAutoCierre() {
        document.querySelectorAll(".mensaje-auto-cierre").forEach(function (mensaje) {
            window.setTimeout(function () {
                mensaje.style.transition = "opacity 0.35s ease, transform 0.35s ease";
                mensaje.style.opacity = "0";
                mensaje.style.transform = "translateY(-8px)";
                window.setTimeout(function () {
                    mensaje.remove();
                }, 380);
            }, 3500);
        });
    }

    function prepararNavegacionConLoader() {
        document.addEventListener("click", function (event) {
            const link = event.target.closest("a");

            if (!link) {
                return;
            }

            if (esNavegacionInternaValida(link, event)) {
                // Se muestra antes de que el navegador cambie de página. Así se
                // ve durante cargas reales de cartelera/APIs/sesiones y no se
                // queda colgado: la página nueva lo oculta en DOMContentLoaded.
                mostrarCarga();
            } else {
                ocultarCarga();
            }
        });

        document.querySelectorAll("form").forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (event.defaultPrevented || esFormularioDeDescargaOArchivo(form)) {
                    ocultarCarga();
                    return;
                }

                if (typeof form.checkValidity === "function" && !form.checkValidity()) {
                    ocultarCarga();
                    return;
                }

                window.setTimeout(function () {
                    if (event.defaultPrevented) {
                        ocultarCarga();
                    }
                }, 0);

                mostrarCarga();
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.body.classList.add("page-is-ready");
        crearOverlay();
        ocultarCarga();
        prepararMensajesAutoCierre();
        prepararNavegacionConLoader();
    });

    window.addEventListener("pageshow", ocultarCarga);
    window.addEventListener("load", ocultarCarga);
    window.addEventListener("focus", function () {
        if (!loaderVisible) {
            ocultarCarga();
        }
    });
})();
