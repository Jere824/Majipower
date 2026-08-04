document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("bill-filter");
    const clear = document.getElementById("clear-bill-filter");

    async function loadBills() {
        const params = new URLSearchParams();
        const status = document.getElementById("bill-status").value;
        const period = document.getElementById("bill-period").value;
        const account = document.getElementById("bill-account").value.trim();
        if (status) params.set("status", status);
        if (period) params.set("billing_period", period);
        if (account) params.set("account", account);

        try {
            const data = await Maji.api(`/api/officer/bills?${params}`);
            document.getElementById("bill-count").textContent = `${data.count} bill${data.count === 1 ? "" : "s"}`;
            document.getElementById("bills-table").innerHTML = data.items.length
                ? data.items.map(item => `
                    <tr>
                        <td>#${item.id}</td>
                        <td><strong>${Maji.escape(item.account_number)}</strong><br><small class="muted">${Maji.escape(item.meter_number)}</small></td>
                        <td>${Maji.escape(item.customer_name)}</td>
                        <td>${Maji.escape(item.billing_period)}</td>
                        <td>${Maji.money(item.total_due)}</td>
                        <td>${Maji.money(item.balance)}</td>
                        <td>${Maji.badge(item.status)}</td>
                        <td>${Maji.escape(item.due_date)}</td>
                        <td><a class="button button-secondary button-small" href="/bills/${item.id}">View</a></td>
                    </tr>`).join("")
                : '<tr><td colspan="9" class="empty-cell">No matching bills.</td></tr>';
        } catch (error) {
            Maji.show(error.message, "error");
        }
    }

    form.addEventListener("submit", event => { event.preventDefault(); loadBills(); });
    clear.addEventListener("click", () => {
        document.getElementById("bill-status").value = "";
        document.getElementById("bill-period").value = "";
        document.getElementById("bill-account").value = "";
        loadBills();
    });
    loadBills();
});
