document.addEventListener("DOMContentLoaded", async () => {
    try {
        const [collections, overdue, revenue] = await Promise.all([
            Maji.api("/api/officer/reports/daily-collections"),
            Maji.api("/api/officer/reports/overdue"),
            Maji.api("/api/officer/reports/revenue")
        ]);

        document.getElementById("collections-report").innerHTML = collections.items.length
            ? collections.items.map(item => `<tr><td>${Maji.escape(item.payment_date)}</td><td>${item.number_of_payments}</td><td>${Maji.money(item.total_collected)}</td></tr>`).join("")
            : '<tr><td colspan="3" class="empty-cell">No confirmed collections found.</td></tr>';

        document.getElementById("overdue-report-count").textContent = `${overdue.count} account${overdue.count === 1 ? "" : "s"}`;
        document.getElementById("overdue-report").innerHTML = overdue.items.length
            ? overdue.items.map(item => `<tr><td><a class="text-link" href="/bills/${item.bill_id}">#${item.bill_id}</a></td><td>${Maji.escape(item.customer_name)}</td><td>${Maji.escape(item.phone)}</td><td>${Maji.escape(item.account_number)}</td><td>${Maji.escape(item.service_type)}</td><td>${Maji.money(item.total_due)}</td><td>${Maji.money(item.balance)}</td><td>${Maji.escape(item.due_date)}</td></tr>`).join("")
            : '<tr><td colspan="8" class="empty-cell">No overdue accounts.</td></tr>';

        const maxRevenue = Math.max(...revenue.items.map(item => Number(item.revenue || 0)), 1);
        document.getElementById("revenue-report").innerHTML = revenue.items.length
            ? revenue.items.map(item => {
                const width = Math.max((Number(item.revenue || 0) / maxRevenue) * 100, 2);
                return `<div class="bar-row"><div class="bar-row-header"><strong>${Maji.escape(item.service_type)}</strong><span>${Maji.money(item.revenue)} · ${item.payment_count} payments</span></div><div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div></div>`;
            }).join("")
            : '<p class="muted">No revenue data found.</p>';
    } catch (error) {
        Maji.show(error.message, "error");
    }
});
