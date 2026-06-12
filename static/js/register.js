document.addEventListener("DOMContentLoaded", () => {
    const usernameInput = document.getElementById("id_username");
    const emailInput = document.getElementById("id_email");
    const usernameStatus = document.getElementById("username-status");
    const emailStatus = document.getElementById("email-status");

    const password1 = document.getElementById("id_password1");
    const password2 = document.getElementById("id_password2");
    const rulesBox = document.getElementById("password-rules");
    const matchText = document.getElementById("password-match");

    const commonPasswords = [
        "password",
        "contraseña",
        "12345678",
        "123456789",
        "qwerty123",
        "admin123",
        "password123",
        "ficinema123"
    ];

    const rules = {
        length: document.getElementById("rule-length"),
        number: document.getElementById("rule-number"),
        letter: document.getElementById("rule-letter"),
        common: document.getElementById("rule-common"),
    };

    function setStatus(element, valid, message) {
        if (!element) return;

        element.textContent = message;
        element.classList.remove("oculto", "valida", "invalida");
        element.classList.add(valid ? "valida" : "invalida");
    }

    function hideStatus(element) {
        if (!element) return;

        element.textContent = "";
        element.classList.add("oculto");
        element.classList.remove("valida", "invalida");
    }

    function debounce(callback, delay = 450) {
        let timer;

        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => callback(...args), delay);
        };
    }

    async function validateRemoteField(fieldName, value, statusElement) {
        const cleanValue = value.trim();

        if (!cleanValue) {
            hideStatus(statusElement);
            return;
        }

        try {
            const params = new URLSearchParams({
                campo: fieldName,
                valor: cleanValue,
            });

            const response = await fetch(`/validar-registro/?${params.toString()}`);
            const data = await response.json();

            setStatus(statusElement, data.valido, data.mensaje);
        } catch (error) {
            setStatus(statusElement, false, "No se pudo validar este campo ahora mismo.");
        }
    }

    const validateUsernameDelayed = debounce(() => {
        validateRemoteField("username", usernameInput.value, usernameStatus);
    });

    const validateEmailDelayed = debounce(() => {
        validateRemoteField("email", emailInput.value, emailStatus);
    });

    if (usernameInput && usernameStatus) {
        usernameInput.addEventListener("input", () => {
            const value = usernameInput.value.trim();

            if (value.length === 0) {
                hideStatus(usernameStatus);
                return;
            }

            validateUsernameDelayed();
        });
    }

    if (emailInput && emailStatus) {
        emailInput.addEventListener("input", () => {
            const value = emailInput.value.trim();

            if (value.length === 0) {
                hideStatus(emailStatus);
                return;
            }

            validateEmailDelayed();
        });
    }

    function setRuleState(element, valid) {
        if (!element) return;

        element.classList.toggle("valida", valid);
        element.classList.toggle("invalida", !valid);
    }

    function validatePassword() {
        if (!password1 || !rulesBox) {
            return false;
        }

        const value = password1.value.trim();
        const lowerValue = value.toLowerCase();

        const validations = {
            length: value.length >= 8,
            number: /\d/.test(value),
            letter: /[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(value),
            common: value.length > 0 && !commonPasswords.includes(lowerValue),
        };

        setRuleState(rules.length, validations.length);
        setRuleState(rules.number, validations.number);
        setRuleState(rules.letter, validations.letter);
        setRuleState(rules.common, validations.common);

        const allValid = Object.values(validations).every(Boolean);

        if (value.length > 0) {
            rulesBox.classList.remove("oculto");
        }

        if (allValid && document.activeElement !== password1) {
            rulesBox.classList.add("oculto");
        }

        validatePasswordMatch();

        return allValid;
    }

    function validatePasswordMatch() {
        if (!password1 || !password2 || !matchText) {
            return false;
        }

        const firstValue = password1.value;
        const secondValue = password2.value;

        if (secondValue.length === 0) {
            hideStatus(matchText);
            return false;
        }

        if (firstValue === secondValue) {
            setStatus(matchText, true, "Las contraseñas coinciden.");

            if (document.activeElement !== password2) {
                setTimeout(() => {
                    matchText.classList.add("oculto");
                }, 1200);
            }

            return true;
        }

        setStatus(matchText, false, "Las contraseñas no coinciden.");
        return false;
    }

    if (password1 && rulesBox) {
        password1.addEventListener("focus", () => {
            if (password1.value.length > 0) {
                rulesBox.classList.remove("oculto");
            }
        });

        password1.addEventListener("input", () => {
            rulesBox.classList.remove("oculto");
            validatePassword();
        });

        password1.addEventListener("blur", () => {
            if (validatePassword()) {
                rulesBox.classList.add("oculto");
            }
        });
    }

    if (password2 && matchText) {
        password2.addEventListener("input", validatePasswordMatch);

        password2.addEventListener("blur", () => {
            if (validatePasswordMatch()) {
                setTimeout(() => {
                    matchText.classList.add("oculto");
                }, 1200);
            }
        });
    }
});