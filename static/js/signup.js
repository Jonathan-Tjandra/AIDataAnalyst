const passwordField = document.getElementById('password');
const confirmPasswordField = document.getElementById('confirm_password');
const submitButton = document.getElementById('submit_button');

const lengthRequirement = document.getElementById('length');
const letterRequirement = document.getElementById('letter');
const numberRequirement = document.getElementById('number');
const matchFeedback = document.getElementById('match_feedback');

// Regex patterns for client-side validation feedback
const hasLetter = /[a-zA-Z]/;
const hasNumber = /\d/;

function checkPasswordStrength() {
    const password = passwordField.value;

    // Check length
    if (password.length >= 8) {
        lengthRequirement.classList.remove('invalid');
        lengthRequirement.classList.add('valid');
    } else {
        lengthRequirement.classList.remove('valid');
        lengthRequirement.classList.add('invalid');
    }

    // Check for letter
    if (hasLetter.test(password)) {
        letterRequirement.classList.remove('invalid');
        letterRequirement.classList.add('valid');
    } else {
        letterRequirement.classList.remove('valid');
        letterRequirement.classList.add('invalid');
    }

    // Check for number
    if (hasNumber.test(password)) {
        numberRequirement.classList.remove('invalid');
        numberRequirement.classList.add('valid');
    } else {
        numberRequirement.classList.remove('valid');
        numberRequirement.classList.add('invalid');
    }

    // Also check password match whenever strength is checked
    checkPasswordMatch(); // Calls updateSubmitButtonState internally
}

function checkPasswordMatch() {
    const password = passwordField.value;
    const confirmPassword = confirmPasswordField.value;

    if (confirmPassword === '') { // Don't show error if confirm is empty
        matchFeedback.style.display = 'none';
    } else if (password === confirmPassword) {
        matchFeedback.style.display = 'none';
    } else {
        matchFeedback.style.display = 'block';
    }

    // Enable/disable submit button based on all criteria
    updateSubmitButtonState();
}

function updateSubmitButtonState() {
    const password = passwordField.value;
    const confirmPassword = confirmPasswordField.value;

    const isPasswordValid = (
        password.length >= 8 &&
        hasLetter.test(password) &&
        hasNumber.test(password)
    );
    const passwordsMatch = (password === confirmPassword && confirmPassword !== '');

    // Only enable if password meets complexity AND passwords match AND confirm password is not empty
    if (isPasswordValid && passwordsMatch && confirmPassword !== '') {
        submitButton.disabled = false;
    } else {
        submitButton.disabled = true;
    }
}

// Initial check when page loads (e.g., if fields are pre-filled by browser)
window.onload = () => {
    checkPasswordStrength(); // This will trigger checkPasswordMatch and updateSubmitButtonState
};