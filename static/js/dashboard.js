document.addEventListener('DOMContentLoaded', () => {

    // --- Element References ---
    const userProfileContainer = document.getElementById('userProfileContainer');
    const userProfileButton = document.getElementById('userProfileButton');
    const userDropdown = document.getElementById('userDropdown');
    const userEmailElement = document.getElementById('userEmail');
    const userNameElement = document.getElementById('userName');
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const fileNameSpan = document.getElementById('fileName');
    const uploadStatus = document.getElementById('upload-status');
    const dataSourceList = document.getElementById('dataSourceList');
    const logoutModal = document.getElementById('logoutModal');
    const deleteModal = document.getElementById('deleteAccountModal');
    const deleteDataSourceModal = document.getElementById('deleteDataSourceModal');
    const confirmDeleteDataSourceBtn = document.getElementById('confirmDeleteDataSourceBtn');
    let dataSourceIdToDelete = null;

    const currentUserEmail = document.body.dataset.userEmail;

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            fileNameSpan.textContent = fileInput.files[0].name;
        } else {
            fileNameSpan.textContent = 'No file chosen';
        }
    });

    // --- Profile Menu Logic ---
    function initializeUserProfile() {
        if (currentUserEmail) {
            const namePart = currentUserEmail.split('@')[0];
            userProfileButton.textContent = namePart.charAt(0).toUpperCase();
            userEmailElement.textContent = currentUserEmail;
            userNameElement.textContent = namePart;
        }
    }
    userProfileButton.addEventListener('click', () => userDropdown.classList.toggle('show'));
    document.addEventListener('click', (event) => {
        if (!userProfileContainer.contains(event.target)) {
            userDropdown.classList.remove('show');
        }
    });

    // --- Data Source Management Logic ---
    async function fetchAndDisplayDataSources() {
        try {
            const response = await fetch('/get_data_sources');
            const data = await response.json();
            dataSourceList.innerHTML = '';
            if (data.success && data.sources.length > 0) {
                data.sources.forEach(source => {
                    const li = document.createElement('li');
                    li.className = 'data-source-item';
                    li.innerHTML = `
                        <div class="data-source-info">
                            <span class="file-type">${source.file_type.toUpperCase()}</span>
                            <span>${source.original_filename}</span>
                        </div>
                        <button class="delete-btn" data-id="${source.id}">Delete</button>`;
                    dataSourceList.appendChild(li);
                });
            } else {
                dataSourceList.innerHTML = '<li>No data sources uploaded yet.</li>';
            }
        } catch (error) {
            dataSourceList.innerHTML = '<li>Could not load data sources.</li>';
        }
    }

    uploadForm.addEventListener('submit', async (event) => {

        event.preventDefault();
        
        if (fileInput.files.length === 0) {
            // Display an error message to the user
            uploadStatus.textContent = 'Please choose a file before uploading.';
            uploadStatus.style.color = 'red';
            
            // Add the shake animation to the input area
            const fileWrapper = document.querySelector('.file-input-wrapper');
            
            // Remove shake class first to allow retriggering
            fileWrapper.classList.remove('shake');
            
            // Force reflow to ensure animation can retrigger
            void fileWrapper.offsetWidth;
            
            // Add the shake class
            fileWrapper.classList.add('shake');
            
            // Remove the shake class and error message after a delay
            setTimeout(() => {
                uploadStatus.textContent = '';
                fileWrapper.classList.remove('shake');
            }, 3000);
            
            return; // Stop the function here
        }
        
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        uploadStatus.textContent = 'Uploading...';
        try {
            const response = await fetch('/upload_data', { method: 'POST', body: formData });
            const result = await response.json();
            uploadStatus.textContent = result.success ? 'Upload successful!' : `Upload failed: ${result.error}`;
            if(result.success) {
                fileInput.value = '';
                fetchAndDisplayDataSources();
            }
        } catch (error) {
            uploadStatus.textContent = 'An error occurred during upload.';
    }
    });

    dataSourceList.addEventListener('click', (event) => {
        if (event.target.classList.contains('delete-btn')) {
            const dataSourceId = event.target.dataset.id;
            showDeleteDataSourceConfirmation(dataSourceId);
        }
    });
    
    // --- Custom Delete Modal Functions ---
    window.showDeleteDataSourceConfirmation = function(id) {
        dataSourceIdToDelete = id; 
        deleteDataSourceModal.classList.add('show');
    }

    window.hideDeleteDataSourceConfirmation = function() {
        dataSourceIdToDelete = null;
        deleteDataSourceModal.classList.remove('show');
    }

    async function confirmDeleteDataSource() {
        if (!dataSourceIdToDelete) return;
        
        const uploadStatus = document.getElementById('upload-status');
        uploadStatus.textContent = 'Deleting...';
        uploadStatus.style.color = 'blue';

        try {
            const response = await fetch(`/delete_data_source/${dataSourceIdToDelete}`, {
                method: 'DELETE',
            });
            const result = await response.json();
            if (result.success) {
                uploadStatus.textContent = 'Data source deleted successfully.';
                uploadStatus.style.color = 'green';
                fetchAndDisplayDataSources();
            } else {
                uploadStatus.textContent = `Error: ${result.error}`;
                uploadStatus.style.color = 'red';
            }
        } catch (error) {
            uploadStatus.textContent = 'An error occurred while deleting the file.';
            uploadStatus.style.color = 'red';
        } finally {
            hideDeleteDataSourceConfirmation();
            setTimeout(() => {
                if (uploadStatus.textContent !== 'Uploading...') {
                    uploadStatus.textContent = '';
                }
            }, 5000);
        }
    }
    
    confirmDeleteDataSourceBtn.addEventListener('click', confirmDeleteDataSource);
    
    // --- Other Modal and Global Functions ---
    window.showLogoutConfirmation = () => { userDropdown.classList.remove('show'); logoutModal.classList.add('show'); };
    window.hideLogoutConfirmation = () => logoutModal.classList.remove('show');
    window.confirmLogout = () => window.location.href = '/logout';
    
    window.showDeleteConfirmation = () => { userDropdown.classList.remove('show'); deleteModal.classList.add('show'); };
    window.hideDeleteConfirmation = () => deleteModal.classList.remove('show');
    
    window.confirmDeleteAccount = async () => {

        const confirmBtn = document.querySelector('#deleteAccountModal .btn-confirm');
        if (confirmBtn) {
            confirmBtn.textContent = 'Deleting...';
            confirmBtn.disabled = true;
        }

        try {
            const response = await fetch('/delete_account', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include'
            });

            const data = await response.json();
            
            // Create elegant notification instead of alert
            const notification = document.createElement('div');
            notification.className = `notification ${data.success ? 'success' : 'error'}`;
            notification.textContent = data.success ? 'Account deleted successfully!' : `Failed to delete account: ${data.error}`;
            document.body.appendChild(notification);
            
            // Auto-remove notification after 3 seconds
            setTimeout(() => notification.remove(), 3000);
            
            if (data.success) window.location.href = '/';
        } catch (error) {
            const notification = document.createElement('div');
            notification.className = 'notification error';
            notification.textContent = 'An error occurred while deleting the account';
            document.body.appendChild(notification);
            setTimeout(() => notification.remove(), 3000);
        } finally {
            // Reset button state even if there's an error
            if (confirmBtn) {
                confirmBtn.textContent = 'Yes, Delete Account';
                confirmBtn.disabled = false;
            }
        }
};
    
    // --- Initial Load ---
    initializeUserProfile();
    fetchAndDisplayDataSources();
});