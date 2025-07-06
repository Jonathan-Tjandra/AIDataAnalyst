const newPasswordField = document.getElementById('new_password');
const confirmNewPasswordField = document.getElementById('confirm_new_password');
const setPasswordButton = document.getElementById('set_password_button');

const newLengthRequirement = document.getElementById('new_length');
const newLetterRequirement = document.getElementById('new_letter');
const newNumberRequirement = document.getElementById('new_number');
const newMatchFeedback = document.getElementById('new_match_feedback');

// Regex patterns for client-side validation feedback
const hasLetter = /[a-zA-Z]/;
const hasNumber = /\d/;

function checkNewPasswordStrength() {
    const password = newPasswordField.value;

    // Check length
    if (password.length >= 8) {
        newLengthRequirement.classList.remove('invalid');
        newLengthRequirement.classList.add('valid');
    } else {
        newLengthRequirement.classList.remove('valid');
        newLengthRequirement.classList.add('invalid');
    }

    // Check for letter
    if (hasLetter.test(password)) {
        newLetterRequirement.classList.remove('invalid');
        newLetterRequirement.classList.add('valid');
    } else {
        newLetterRequirement.classList.remove('valid');
        newLetterRequirement.classList.add('invalid');
    }

    // Check for number
    if (hasNumber.test(password)) {
        newNumberRequirement.classList.remove('invalid');
        newNumberRequirement.classList.add('valid');
    } else {
        newNumberRequirement.classList.remove('valid');
        newNumberRequirement.classList.add('invalid');
    }

    // Also check password match whenever strength is checked
    checkNewPasswordMatch(); // Calls updateSubmitButtonState internally
}

function checkNewPasswordMatch() {
    const password = newPasswordField.value;
    const confirmPassword = confirmNewPasswordField.value;

    if (confirmPassword === '') { // Don't show error if confirm is empty
        newMatchFeedback.style.display = 'none';
    } else if (password === confirmPassword) {
        newMatchFeedback.style.display = 'none';
    } else {
        newMatchFeedback.style.display = 'block';
    }

    // Enable/disable submit button based on all criteria
    updateSetPasswordButtonState();
}

function updateSetPasswordButtonState() {
    const password = newPasswordField.value;
    const confirmPassword = confirmNewPasswordField.value;

    const isPasswordValid = (
        password.length >= 8 &&
        hasLetter.test(password) &&
        hasNumber.test(password)
    );
    const passwordsMatch = (password === confirmPassword && confirmPassword !== '');

    // Only enable if password meets complexity AND passwords match AND confirm password is not empty
    if (isPasswordValid && passwordsMatch && confirmPassword !== '') {
        setPasswordButton.disabled = false;
    } else {
        setPasswordButton.disabled = true;
    }
}

// Initial check when page loads (e.g., if fields are pre-filled by browser)
window.onload = () => {
    checkNewPasswordStrength(); // This will trigger checkNewPasswordMatch and updateSetPasswordButtonState
};