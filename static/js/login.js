(function () {
    "use strict";

    const form = document.getElementById("login-form");
    const button = document.getElementById("login-button");
    const alertBox = document.getElementById("login-alert");

    function show(message) {
        alertBox.textContent = message;
        alertBox.className = "alert alert-error";
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        alertBox.className = "alert hidden";
        button.disabled = true;
        button.textContent = "Signing in…";

        try {
            const response = await fetch("/api/auth/login", {
                method: "POST",
                credentials: "same-origin",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    phone: document.getElementById("phone").value.trim(),
                    password: document.getElementById("password").value
                })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Login failed.");

            if (!["billing_officer", "admin"].includes(data.user.role)) {
                await fetch("/api/auth/logout", {method: "POST", credentials: "same-origin"});
                throw new Error("This portal is restricted to Billing Officers and Administrators.");
            }

            window.location.href = "/dashboard";
        } catch (error) {
            show(error.message);
            button.disabled = false;
            button.textContent = "Sign in";
        }
    });
})();
