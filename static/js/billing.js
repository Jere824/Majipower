document.addEventListener("DOMContentLoaded", () => {
    const periodInput = document.getElementById("billing-period");
    const dueDateInput = document.getElementById("due-date");
    const form = document.getElementById("billing-form");
    const previewButton = document.getElementById("preview-button");
    const generateButton = document.getElementById("generate-button");
    const overdueButton = document.getElementById("process-overdue-button");
    let currentPreview = null;

    const today = new Date();
    periodInput.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
    const dueDate = new Date(today);
    dueDate.setDate(dueDate.getDate() + 14);
    dueDateInput.value = dueDate.toISOString().slice(0, 10);

    function previewPayload() {
        return {
            billing_period: periodInput.value,
            due_date: dueDateInput.value,
            service_type: document.getElementById("billing-service").value || null
        };
    }

    function renderPreview(data) {
        currentPreview = data;
        document.getElementById("preview-section").classList.remove("hidden");
        document.getElementById("preview-total").textContent = data.items.length;
        document.getElementById("preview-ready").textContent = data.ready_to_generate;
        document.getElementById("preview-exceptions").textContent = data.exceptions.length;
        generateButton.disabled = data.ready_to_generate === 0;

        document.getElementById("billing-preview-table").innerHTML = data.items.map(item => {
            const outcome = item.exception
                ? `<span class="badge badge-failed">${Maji.escape(item.exception)}</span>`
                : item.warning
                    ? `<span class="badge badge-pending">${Maji.escape(item.warning)}</span>`
                    : '<span class="badge badge-paid">Ready</span>';
            return `<tr>
                <td><strong>${Maji.escape(item.account_number)}</strong></td>
                <td>${Maji.escape(item.customer_name)}</td>
                <td>${Maji.escape(item.service_type)}</td>
                <td>${item.consumption == null ? "—" : Maji.number(item.consumption)}</td>
                <td>${item.consumption_charge == null ? "—" : Maji.money(item.consumption_charge + item.fixed_charge + item.tax_amount)}</td>
                <td>${item.total_due == null ? "—" : Maji.money(item.total_due)}</td>
                <td>${outcome}</td>
            </tr>`;
        }).join("");
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        Maji.clear();
        Maji.setBusy(previewButton, true, "Preparing…");
        try {
            const data = await Maji.api("/api/officer/billing/preview-bulk", {
                method: "POST",
                body: JSON.stringify(previewPayload())
            });
            renderPreview(data);
            Maji.show("Billing preview completed. Review warnings before generation.", "success");
        } catch (error) {
            Maji.show(error.message, "error");
        } finally {
            Maji.setBusy(previewButton, false);
        }
    });

    generateButton.addEventListener("click", async () => {
        if (!currentPreview || currentPreview.ready_to_generate === 0) return;
        if (!window.confirm(`Generate ${currentPreview.ready_to_generate} valid bill(s)?`)) return;
        Maji.setBusy(generateButton, true, "Generating…");
        try {
            const result = await Maji.api("/api/officer/bills/bulk", {
                method: "POST",
                body: JSON.stringify(previewPayload())
            });
            Maji.show(`${result.generated_count} bill(s) generated successfully.`, "success");
            const refreshed = await Maji.api("/api/officer/billing/preview-bulk", {
                method: "POST",
                body: JSON.stringify(previewPayload())
            });
            renderPreview(refreshed);
        } catch (error) {
            Maji.show(error.message, "error");
        } finally {
            Maji.setBusy(generateButton, false);
        }
    });

    overdueButton.addEventListener("click", async () => {
        if (!window.confirm("Mark all past-due issued bills as overdue and apply penalties?")) return;
        Maji.setBusy(overdueButton, true, "Processing…");
        try {
            const result = await Maji.api("/api/officer/bills/process-overdue", {
                method: "POST",
                body: JSON.stringify({apply_penalty: true})
            });
            Maji.show(`${result.count} bill(s) processed as overdue.`, "success");
        } catch (error) {
            Maji.show(error.message, "error");
        } finally {
            Maji.setBusy(overdueButton, false);
        }
    });
});
