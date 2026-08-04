document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("payment-filter");

    async function updateStatus(paymentId, status) {
        const label = status === "confirmed" ? "confirm" : `mark as ${status}`;
        if (!window.confirm(`Are you sure you want to ${label} payment #${paymentId}?`)) return;
        try {
            await Maji.api(`/api/officer/payments/${paymentId}/status`, {
                method: "PATCH",
                body: JSON.stringify({status})
            });
            Maji.show(`Payment #${paymentId} updated to ${status}.`, "success");
            await loadPayments();
        } catch (error) {
            Maji.show(error.message, "error");
        }
    }

    async function loadPayments() {
        const params = new URLSearchParams();
        const values = {
            status: document.getElementById("payment-status").value,
            method: document.getElementById("payment-method").value,
            account: document.getElementById("payment-account").value.trim(),
            billing_period: document.getElementById("payment-period").value
        };
        Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); });

        try {
            const data = await Maji.api(`/api/officer/payments?${params}`);
            document.getElementById("payment-count").textContent = `${data.count} payment${data.count === 1 ? "" : "s"}`;
            document.getElementById("payments-table").innerHTML = data.items.length
                ? data.items.map(item => {
                    const actions = ["pending", "initiated"].includes(item.status)
                        ? `<div style="display:flex;gap:6px;flex-wrap:wrap"><button class="button button-success button-small" data-payment="${item.id}" data-status="confirmed">Confirm</button><button class="button button-danger button-small" data-payment="${item.id}" data-status="failed">Fail</button></div>`
                        : "—";
                    return `<tr>
                        <td>#${item.id}</td>
                        <td><strong>${Maji.escape(item.account_number)}</strong></td>
                        <td>${Maji.escape(item.customer_name)}</td>
                        <td>${Maji.escape(item.payment_method).replaceAll("_", " ")}</td>
                        <td>${Maji.money(item.amount)}</td>
                        <td>${Maji.escape(item.provider_reference || "—")}</td>
                        <td>${Maji.badge(item.status)}</td>
                        <td>${Maji.escape(item.created_at)}</td>
                        <td>${actions}</td>
                    </tr>`;
                }).join("")
                : '<tr><td colspan="9" class="empty-cell">No matching payments.</td></tr>';

            document.querySelectorAll("[data-payment][data-status]").forEach(button => {
                button.addEventListener("click", () => updateStatus(button.dataset.payment, button.dataset.status));
            });
        } catch (error) {
            Maji.show(error.message, "error");
        }
    }

    form.addEventListener("submit", event => { event.preventDefault(); loadPayments(); });
    loadPayments();
});
