document.addEventListener("DOMContentLoaded", function () {
    const backdrop = document.createElement("div");
    backdrop.className = "nav-backdrop";
    backdrop.setAttribute("aria-hidden", "true");
    document.body.appendChild(backdrop);

    document.querySelectorAll(".nav-toggle").forEach(function (toggle, index) {
        const nav = toggle.closest(".main-nav");
        const links = nav ? nav.querySelector(".nav-links") : null;

        if (links && !links.id) {
            links.id = "main-navigation-" + index;
        }

        if (links) {
            toggle.setAttribute("aria-controls", links.id);
        }

        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Abrir menú principal");
    });

    document.querySelectorAll(".nav-active").forEach(function (item) {
        item.setAttribute("aria-current", "page");
    });

    function cerrarMenus() {
        document.querySelectorAll(".nav-links.nav-links-open").forEach(function (links) {
            links.classList.remove("nav-links-open");
        });

        document.querySelectorAll(".nav-toggle[aria-expanded='true']").forEach(function (toggle) {
            toggle.setAttribute("aria-expanded", "false");
            toggle.setAttribute("aria-label", "Abrir menú principal");
        });

        document.querySelectorAll(".nav-dropdown[open]").forEach(function (dropdown) {
            dropdown.removeAttribute("open");
        });

        backdrop.classList.remove("is-visible");
        document.body.classList.remove("nav-open");
    }

    function abrirMenu(nav, toggle) {
        const links = nav.querySelector(".nav-links");

        if (!links) {
            return;
        }

        links.classList.add("nav-links-open");
        toggle.setAttribute("aria-expanded", "true");
        toggle.setAttribute("aria-label", "Cerrar menú principal");
        backdrop.classList.add("is-visible");
        document.body.classList.add("nav-open");
    }

    document.querySelectorAll(".nav-toggle").forEach(function (toggle) {
        toggle.addEventListener("click", function () {
            const nav = toggle.closest(".main-nav");
            const links = nav ? nav.querySelector(".nav-links") : null;

            if (!nav || !links) {
                return;
            }

            if (links.classList.contains("nav-links-open")) {
                cerrarMenus();
            } else {
                abrirMenu(nav, toggle);
            }
        });
    });

    backdrop.addEventListener("click", cerrarMenus);

    document.addEventListener("click", function (event) {
        document.querySelectorAll(".nav-dropdown[open]").forEach(function (dropdown) {
            if (!dropdown.contains(event.target)) {
                dropdown.removeAttribute("open");
            }
        });
    });

    document.querySelectorAll(".nav-dropdown-menu a, .nav-links > a").forEach(function (link) {
        link.addEventListener("click", function () {
            cerrarMenus();
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            cerrarMenus();
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 1180) {
            cerrarMenus();
        }
    });
});
