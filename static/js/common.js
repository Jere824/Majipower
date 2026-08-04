(function () {
    "use strict";

    window.Maji = {
        async api(url, options = {}) {
            const config = {
                credentials: "same-origin",
                ...options,
                headers: {
                    ...(options.body ? {"Content-Type": "application/json"} : {}),
                    ...(options.headers || {})
                }
            };

            const response = await fetch(url, config);
            const contentType = response.headers.get("content-type") || "";
            const data = contentType.includes("application/json")
                ? await response.json()
                : {error: await response.text()};

            if (response.status === 401) {
                window.location.href = "/login";
                throw new Error(data.error || "Your session has expired.");
            }

            if (!response.ok) {
                throw new Error(data.error || "The request could not be completed.");
            }

            return data;
        },

        money(value) {
            return new Intl.NumberFormat("en-KE", {
                style: "currency",
                currency: "KES",
                maximumFractionDigits: 2
            }).format(Number(value || 0));
        },

        number(value) {
            return new Intl.NumberFormat("en-KE", {maximumFractionDigits: 2}).format(Number(value || 0));
        },

        escape(value) {
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        },

        badge(status) {
            const safe = this.escape(status || "unknown");
            const cls = safe.toLowerCase().replaceAll(" ", "_");
            const label = safe.replaceAll("_", " ");
            return `<span class="badge badge-${cls}">${label}</span>`;
        },

        show(message, kind = "info", targetId = "global-alert") {
            const element = document.getElementById(targetId);
            if (!element) return;
            element.textContent = message;
            element.className = `alert alert-${kind}`;
            element.scrollIntoView({behavior: "smooth", block: "nearest"});
        },

        clear(targetId = "global-alert") {
            const element = document.getElementById(targetId);
            if (!element) return;
            element.textContent = "";
            element.className = "alert hidden";
        },

        setBusy(button, busy, busyText = "Working…") {
            if (!button) return;
            if (busy) {
                button.dataset.originalText = button.textContent;
                button.textContent = busyText;
                button.disabled = true;
            } else {
                button.textContent = button.dataset.originalText || button.textContent;
                button.disabled = false;
            }
        }
    };

    document.addEventListener("DOMContentLoaded", async () => {
        const menuButton = document.getElementById("menu-button");
        const sidebar = document.getElementById("sidebar");
        menuButton?.addEventListener("click", () => sidebar?.classList.toggle("open"));

        const logoutButton = document.getElementById("logout-button");
        logoutButton?.addEventListener("click", async () => {
            Maji.setBusy(logoutButton, true, "Logging out…");
            try {
                await Maji.api("/api/auth/logout", {method: "POST"});
                window.location.href = "/login";
            } catch (error) {
                Maji.show(error.message, "error");
                Maji.setBusy(logoutButton, false);
            }
        });

        try {
            const user = await Maji.api("/api/auth/me");
            const name = document.getElementById("current-user-name");
            const sidebarUser = document.getElementById("sidebar-user");
            const sidebarRole = document.getElementById("sidebar-role");
            if (name) name.textContent = user.name;
            if (sidebarUser) sidebarUser.textContent = user.name;
            if (sidebarRole) sidebarRole.textContent = user.role.replaceAll("_", " ");
        } catch (_) {
            // Maji.api handles expired sessions by redirecting to /login.
        }
    });
})();
