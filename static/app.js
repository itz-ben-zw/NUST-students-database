const studentSelect = document.querySelector('#student-select');
const currencySelect = document.querySelector('#currency-select');
const amountInput = document.querySelector('input[name="amount"]');

if (studentSelect && currencySelect && amountInput) {
  studentSelect.addEventListener('change', () => {
    const option = studentSelect.selectedOptions[0];
    if (option?.dataset.currency) currencySelect.value = option.dataset.currency;
    if (option?.dataset.balance) amountInput.max = (Number(option.dataset.balance) / 100).toFixed(2);
  });
}
