// static/js/user_form.js
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('user-form');
    if (form) {
        // Phone number validation
        const phoneInput = form.querySelector('[name="phone_number"]');
        if (phoneInput) {
            phoneInput.addEventListener('blur', function() {
                const phone = this.value.trim();
                if (phone && !/^(\+254|0|254|7)\d{8,9}$/.test(phone.replace(/[^\d]/g, ''))) {
                    this.setCustomValidity('Please enter a valid Kenyan phone number');
                } else {
                    this.setCustomValidity('');
                }
            });
        }

        // Password strength indicator could be added here
    }
});
