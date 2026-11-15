const studentSelect = document.querySelector('#student-select');
const currencySelect = document.querySelector('#currency-select');
const amountInput = document.querySelector('input[name="amount"]');

if (studentSelect && currencySelect && amountInput) {
  const updateAmountLimit = () => {
    const option = studentSelect.selectedOptions[0];
    if (option?.dataset.balance) {
      amountInput.max = (Number(option.dataset.balance) / 100).toFixed(2);
    } else {
      amountInput.removeAttribute('max');
    }
  };

  studentSelect.addEventListener('change', () => {
    const option = studentSelect.selectedOptions[0];
    if (option?.dataset.currency) currencySelect.value = option.dataset.currency;
    updateAmountLimit();
  });

  updateAmountLimit();
}
