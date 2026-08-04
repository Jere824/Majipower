document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("account-filter");
    const clear = document.getElementById("clear-account-filter");

    async function loadAccounts() {
        const params = new URLSearchParams();
        const search = document.getElementById("account-search").value.trim();
        const serviceType = document.getElementById("service-type").value;
        if (search) params.set("search", search);
        if (serviceType) params.set("service_type", serviceType);

        try {
            const data = await Maji.api(`/api/officer/accounts?${params}`);
            document.getElementById("account-count").textContent = `${data.count} account${data.count === 1 ? "" : "s"}`;
            document.getElementById("accounts-table").innerHTML = data.items.length
                ? data.items.map(item => `
                    <tr>
                        <td><strong>${Maji.escape(item.account_number)}</strong></td>
                        <td>${Maji.escape(item.customer_name)}<br><small class="muted">${Maji.escape(item.customer_phone)}</small></td>
                        <td>${Maji.escape(item.meter_number)}</td>
                        <td>${Maji.badge(item.service_type)}</td>
                        <td>${Maji.escape(item.address)}</td>
                        <td>${item.latest_reading == null ? "—" : Maji.number(item.latest_reading)}</td>
                    </tr>`).join("")
                : '<tr><td colspan="6" class="empty-cell">No matching accounts.</td></tr>';
        } catch (error) {
            Maji.show(error.message, "error");
        }
    }

    form.addEventListener("submit", event => { event.preventDefault(); loadAccounts(); });
    clear.addEventListener("click", () => {
        document.getElementById("account-search").value = "";
        document.getElementById("service-type").value = "";
        loadAccounts();
    });
    loadAccounts();
});
