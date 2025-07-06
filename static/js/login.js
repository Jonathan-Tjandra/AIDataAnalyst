function togglePasswordVisibility() {
    const passwordField = document.getElementById('password');
    const toggleButton = document.querySelector('.password-toggle');
    if (passwordField.type === 'password') {
        passwordField.type = 'text';
        toggleButton.textContent = 'Hide';
    } else {
        passwordField.type = 'password';
        toggleButton.textContent = 'Show';
    }
}

function showLoadingIndicator() {
    // The 'flex' display style comes from our CSS for centering
    document.getElementById('global-loading-overlay').style.display = 'flex';
}

function hideLoadingIndicator() {
    document.getElementById('global-loading-overlay').style.display = 'none';
}

// 3. JavaScript Callback Function for Google Sign-In
function handleCredentialResponse(response) {

    const id_token = response.credential;
    const backend_url = '/auth/google/callback';

    // Show the loading indicator right before starting the fetch
    showLoadingIndicator();

    fetch(backend_url, {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({ token: id_token })
    })
    .then(res => {
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
    })
    .then(data => {
        console.log("Backend response:", data);
        if (data.success) {
            // On success, the page will redirect, hiding the loader automatically
            window.location.href = '/dashboard';
        } else {
            // On failure, alert the user
            alert('Google Authentication failed: ' + (data.message || 'Please try again.'));
        }
    })
    .catch(error => {
        console.error('Error sending token to backend:', error);
        alert('An error occurred during sign-in: ' + error.message);
    })
    .finally(() => {
        // This will always run, hiding the loader if an error occurred
        hideLoadingIndicator();
    });
    
}

// 4. JS for login form
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');

    if (loginForm) {
        loginForm.addEventListener('submit', async (event) => {
            // 1. Prevent the browser's default form submission
            event.preventDefault();
            
            // 2. Show the loading indicator
            showLoadingIndicator();

            try {
                const formData = new FormData(loginForm);
                const response = await fetch(loginForm.action, {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    // On successful login, redirect to the dashboard
                    requestAnimationFrame(() => {
                        window.location.href = '/dashboard';
                    });
                } else {
                    // If login fails (e.g., wrong password), hide loader and alert user
                    hideLoadingIndicator();
                    alert('Login failed. Please check your email and password.');
                }
            } catch (error) {
                // If there's a network error, hide loader and alert user
                hideLoadingIndicator();
                console.error('Error during login:', error);
                alert('An error occurred. Please try again later.');
            }
        });
    }
});