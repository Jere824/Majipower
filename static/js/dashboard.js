document.addEventListener("DOMContentLoaded", async () => {
    try {
        const [dashboard, bills] = await Promise.all([
            Maji.api("/api/officer/dashboard"),
            Maji.api("/api/officer/bills")
        ]);

        document.getElementById("readings-received").textContent = Maji.number(dashboard.readings_received);
        document.getElementById("bills-to-generate").textContent = Maji.number(dashboard.bills_to_generate);
        document.getElementById("overdue-accounts").textContent = Maji.number(dashboard.overdue_accounts);
        document.getElementById("collections-today").textContent = Maji.money(dashboard.collections_today);
        document.getElementById("outstanding-balance").textContent = Maji.money(dashboard.outstanding_balance);

        const rows = bills.items.slice(0, 5);
        document.getElementById("recent-bills").innerHTML = rows.length
            ? rows.map(item => `
                <tr>
                    <td><a class="text-link" href="/bills/${item.id}">${Maji.escape(item.account_number)}</a></td>
                    <td>${Maji.money(item.total_due)}</td>
                    <td>${Maji.badge(item.status)}</td>
                </tr>`).join("")
            : '<tr><td colspan="3" class="empty-cell">No bills found.</td></tr>';
    } catch (error) {
        Maji.show(error.message, "error");
    }
});
