document.addEventListener("DOMContentLoaded", async () => {
    const billId = document.getElementById("bill-detail-root").dataset.billId;
    try {
        const bill = await Maji.api(`/api/officer/bills/${billId}`);
        document.getElementById("bill-heading").textContent = `Bill #${bill.id}`;
        document.getElementById("bill-customer").textContent = `${bill.customer_name} · ${bill.customer_phone}`;
        document.getElementById("bill-detail-status").outerHTML = Maji.badge(bill.status);
        document.getElementById("detail-account").textContent = `${bill.account_number} / ${bill.meter_number}`;
        document.getElementById("detail-period").textContent = bill.billing_period;
        document.getElementById("detail-due-date").textContent = bill.due_date;
        document.getElementById("detail-consumption").textContent = Maji.number(bill.consumption);
        document.getElementById("charge-previous").textContent = Maji.money(bill.previous_balance);
        document.getElementById("charge-consumption").textContent = Maji.money(bill.consumption_charge);
        document.getElementById("charge-fixed").textContent = Maji.money(bill.fixed_charge);
        document.getElementById("charge-tax").textContent = Maji.money(bill.tax_amount);
        document.getElementById("charge-penalty").textContent = Maji.money(bill.penalty_amount);
        document.getElementById("charge-total").textContent = Maji.money(bill.total_due);
        document.getElementById("charge-paid").textContent = Maji.money(bill.paid_amount);
        document.getElementById("charge-balance").textContent = Maji.money(bill.balance);
        document.getElementById("bill-payments").innerHTML = bill.payments.length
            ? bill.payments.map(payment => `<tr><td>#${payment.id}</td><td>${Maji.escape(payment.payment_method).replaceAll("_", " ")}</td><td>${Maji.money(payment.amount)}</td><td>${Maji.badge(payment.status)}</td></tr>`).join("")
            : '<tr><td colspan="4" class="empty-cell">No payments recorded for this bill.</td></tr>';
    } catch (error) {
        Maji.show(error.message, "error");
    }
});
