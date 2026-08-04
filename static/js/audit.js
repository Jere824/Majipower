document.addEventListener("DOMContentLoaded", async () => {
    try {
        const data = await Maji.api("/api/officer/audit-log?limit=200");
        document.getElementById("audit-table").innerHTML = data.items.length
            ? data.items.map(item => `<tr><td>${Maji.escape(item.created_at)}</td><td>${Maji.escape(item.user_name || "System")}</td><td>${Maji.escape((item.user_role || "—").replaceAll("_", " "))}</td><td>${Maji.escape(item.action).replaceAll("_", " ")}</td><td>${Maji.escape(item.target)}</td><td>${Maji.escape(item.detail || "—")}</td></tr>`).join("")
            : '<tr><td colspan="6" class="empty-cell">No audit activity found.</td></tr>';
    } catch (error) {
        Maji.show(error.message, "error");
    }
});
