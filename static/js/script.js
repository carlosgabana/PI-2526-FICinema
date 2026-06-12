document.addEventListener("DOMContentLoaded", () => {
    const selectorOrden = document.querySelector('select[name="ordenar_por"]');

    if (selectorOrden) {
        selectorOrden.addEventListener("change", () => {
            const val = encodeURIComponent(selectorOrden.value);
            window.location.href = `?ordenar_por=${val}`;
        });
    }

    const selectorFecha = document.getElementById('fecha');
    const contenedorSesiones = document.getElementById('contenedor-horas');

    if (selectorFecha && contenedorSesiones) {
        actualizarSesiones();
    }
});

function actualizarSesiones() {
    const selector = document.getElementById('fecha');
    const contenedorSesiones = document.getElementById('contenedor-horas');

    if (!selector || !contenedorSesiones || selector.selectedIndex < 0) {
        return;
    }

    const fechaSeleccionada = selector.options[selector.selectedIndex];
    const numeroDia = parseInt(fechaSeleccionada.getAttribute('data-numero'));

    let horarios = [];

    if (numeroDia % 2 === 0) {
        horarios = ['12:00', '17:00', '22:00'];
    } else {
        horarios = ['14:00', '19:00'];
    }

    contenedorSesiones.innerHTML = '';

    horarios.forEach(horario => {
        const boton = document.createElement('button');
        boton.className = 'hora-btn';
        boton.innerText = horario;
        boton.onclick = function () {
            seleccionarSesion(this);
        };
        contenedorSesiones.appendChild(boton);
    });
}

function seleccionarSesion(boton) {
    const botones = document.querySelectorAll('.hora-btn');
    botones.forEach(btn => btn.classList.remove('seleccionada'));
    boton.classList.add('seleccionada');
}