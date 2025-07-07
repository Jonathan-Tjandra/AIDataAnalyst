document.addEventListener('DOMContentLoaded', () => {
    // --- START: Element Selection ---
    const sidebar = document.querySelector('.sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const userInput = document.getElementById('user-input');
    const csvFileSelector = document.getElementById('csv-file-selector');
    const sendBtn = document.getElementById('send-btn');
    const stopBtn = document.getElementById('stop-btn');
    const chatMessages = document.querySelector('.chat-messages');
    const newChatBtn = document.querySelector('.new-chat-btn');
    const deleteChatBtn = document.querySelector('.delete-chat-btn');
    const chatHistoryContainer = document.querySelector('.chat-history');
    // --- END: Element Selection ---

    // --- START: State Management ---
    let currentSessionId = null;
    // --- END: State Management ---

    // --- START: Sidebar Toggle Functionality ---
    const handleSidebarToggle = () => {
        sidebar.classList.toggle('collapsed');
        const isCollapsed = sidebar.classList.contains('collapsed');
        const icon = sidebarToggle.querySelector('.icon');
        const text = sidebarToggle.querySelector('.text');
        if (isCollapsed) {
            icon.innerHTML = '&raquo;';
            text.textContent = 'Expand';
            sidebarToggle.title = 'Expand sidebar';
        } else {
            icon.innerHTML = '&laquo;';
            text.textContent = 'Collapse';
            sidebarToggle.title = 'Collapse sidebar';
        }
    };
    // --- END: Sidebar Toggle Functionality ---

    // --- START: Send Button Enable/Disable Logic ---
   const updateSendButtonState = () => {
        const hasText = userInput.value.trim() !== '';
        const hasFile = csvFileSelector.value !== '';
        
        // Check if current session is generating
        const sessionState = sessionLoadingStates.get(currentSessionId);
        const isCurrentSessionGenerating = sessionState && sessionState.isGenerating;
        
        // Enable send button only if there is text, a file is selected, AND the current session is not generating
        sendBtn.disabled = !hasText || !hasFile || isCurrentSessionGenerating;
    };
    // --- END: Send Button Enable/Disable Logic ---


    // --- START: Elegant Confirmation Modal ---
    const showConfirmationModal = (message, onConfirm) => {
        // Remove any existing modal
        const existingModal = document.querySelector('.confirmation-modal-overlay');
        if (existingModal) existingModal.remove();

        // Create overlay and modal elements
        const overlay = document.createElement('div');
        overlay.className = 'confirmation-modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'confirmation-modal';

        const modalMessage = document.createElement('p');
        modalMessage.textContent = message;

        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'modal-button-group';

        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = 'Confirm';
        confirmBtn.className = 'modal-confirm-btn';

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';
        cancelBtn.className = 'modal-cancel-btn';

        // Event listeners
        const closeModal = () => overlay.remove();
        cancelBtn.addEventListener('click', closeModal);
        confirmBtn.addEventListener('click', () => {
            onConfirm();
            closeModal();
        });

        // Assemble modal
        buttonGroup.append(cancelBtn, confirmBtn);
        modal.append(modalMessage, buttonGroup);
        overlay.append(modal);
        document.body.appendChild(overlay);
    };
    // --- END: Elegant Confirmation Modal ---

    // --- START: Add Message to UI ---
   const addMessageToChat = (sender, content) => {
        const messageBubble = document.createElement('div');
        messageBubble.classList.add('message-bubble', `${sender}-message`);

        // Path 1: Content is a file object
        if (typeof content === 'object' && content !== null && content.type === 'file') {
            const fileContainer = document.createElement('div');
            fileContainer.className = 'file-container';

            if (content.is_deleted) {
                fileContainer.classList.add('deleted');
                fileContainer.innerHTML = `
                    <div class="deleted-file-notice">
                        <span class="deleted-icon">🗑️</span>
                        <span>File deleted</span>
                    </div>
                `;
            } else {
                const fileId = content.id || content.file_id;
                
                if (!fileId) {
                    console.error('File ID is missing from content:', content);
                    messageBubble.innerHTML = `<div class="file-error">❌ File data is corrupt. ID missing.</div>`;
                    chatMessages.appendChild(messageBubble);
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                    return messageBubble;
                }

                const introMessage = document.createElement('div');
                introMessage.className = 'file-intro-message';
                introMessage.textContent = content.intro_message || 'Here is the generated file:';

                const filePreview = document.createElement('div');
                filePreview.className = 'file-preview';
                const fileType = content.file_type || 'unknown';
            
                if (fileType.includes('image')) {
                    const img = document.createElement('img');
                    img.src = `/api/files/${fileId}/download`;
                    img.className = 'file-preview-image';
                    img.alt = `Generated ${fileType}`;
                    img.onerror = function() {
                        this.style.display = 'none';
                        filePreview.innerHTML = `<div class="file-preview-placeholder"><span class="file-icon">🖼️</span><span>Image preview unavailable</span></div>`;
                    };
                    filePreview.appendChild(img);
                } else {
                    const icon = (fileType === 'csv') ? '📄' : '📁';
                    filePreview.innerHTML = `<div class="file-preview-placeholder"><span class="file-icon">${icon}</span><span>${fileType.toUpperCase()} File - Click to download</span></div>`;
                }

                const fileButtons = document.createElement('div');
                fileButtons.className = 'file-buttons';

                const downloadBtn = document.createElement('a');
                downloadBtn.textContent = '⬇️ Download';
                downloadBtn.href = `/api/files/${fileId}/download`;
                downloadBtn.target = '_blank';
                downloadBtn.className = 'file-download-btn';

                const deleteBtn = document.createElement('button');
                deleteBtn.innerHTML = '🗑️ Delete';
                deleteBtn.className = 'file-delete-btn';
                deleteBtn.onclick = () => {
                    showConfirmationModal('Are you sure you want to delete this file? This cannot be undone.', () => {
                        showLoadingIndicator(); 
                        fetch(`/api/files/${fileId}`, { method: 'DELETE' })
                            .then(response => {
                                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                                return response.json();
                            })
                            .then(data => {
                               
                                messageBubble.innerHTML = `
                                    <div class="deleted-file-notice">
                                        <span class="deleted-icon">🗑️</span>
                                        <span>File deleted</span>
                                    </div>
                                `;
                                messageBubble.classList.add('deleted');
                            })
                            .catch(err => {
                                console.error("Error deleting file:", err);
                                alert("Error deleting file. Please check the console and try again.");
                            })
                            .finally(() => {
                                hideLoadingIndicator(); 
                            });
                    });
                };

                fileButtons.append(downloadBtn, deleteBtn);
                fileContainer.append(introMessage, filePreview, fileButtons);
            }
            messageBubble.appendChild(fileContainer);

        // Path 2: Handle text content
        } else {
            const text = (typeof content === 'object' && content !== null && content.text) ? content.text : content;
            messageBubble.textContent = text;
        }

        chatMessages.appendChild(messageBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        return messageBubble;
    };

    // --- END: Add Message to UI ---


   const loadChat = async (sessionId) => {
        hideAILoadingIndicator(); // Hide loading indicator from previous session
        
        showLoadingIndicator(); // This is for loading chat history
        
        try {
            const response = await fetch(`/api/sessions/${sessionId}`);
            if (!response.ok) throw new Error('Failed to load messages');
            
            const data = await response.json();
            console.log('=== LOADING CHAT SESSION ===');
            console.log('Session ID:', sessionId);
            console.log('Backend response:', data);
            console.log('Number of messages:', data.messages.length);
            
            const messages = data.messages;
            
            currentSessionId = parseInt(sessionId);
            chatMessages.innerHTML = '';
            
            messages.forEach((msg, index) => {
                console.log(`Message ${index}:`, {
                    sender: msg.sender,
                    message_type: msg.message_type,
                    content_type: typeof msg.content,
                    content: msg.content
                });
                
                // Add message to chat
                addMessageToChat(msg.sender, msg.content, msg.message_type);
            });
            
            console.log('=== CHAT LOADING COMPLETE ===');
            
            // Update active state in UI
            document.querySelectorAll('.chat-history-item').forEach(item => {
                item.classList.remove('active');
            });
            const activeItem = document.querySelector(`[data-session-id="${sessionId}"]`);
            if (activeItem) {
                activeItem.classList.add('active');
            }
            
            // Check if this session is generating and update UI accordingly
            const sessionState = sessionLoadingStates.get(currentSessionId);
            if (sessionState && sessionState.isGenerating) {
                // Show loading and update buttons if this session is generating
                sendBtn.classList.add('button-hidden');
                stopBtn.classList.remove('button-hidden');
                showAILoadingIndicator();
            } else {
                // Hide loading and update buttons if this session is not generating
                sendBtn.classList.remove('button-hidden');
                stopBtn.classList.add('button-hidden');
                hideAILoadingIndicator();
            }
            updateSendButtonState();
            
        } catch (error) {
            console.error('Error loading chat:', error);
        }
        finally{
            hideLoadingIndicator(); // Hide chat loading indicator
        }
    };

    const createNewChatSession = async () => {

        showLoadingIndicator();
        hideAILoadingIndicator();

        try {
            const response = await fetch('/api/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Failed to create a new session on the server.');
            }

            const newSession = await response.json(); // Gets { "id": 123, "title": "New Chat" }

            // Set the current session to the REAL ID from the database
            currentSessionId = newSession.id;

            // Clear the chat UI for the new session
            chatMessages.innerHTML = '';

            // Add the new session to the top of the sidebar UI
            const historyItem = createSessionElement(newSession);

            document.querySelectorAll('.chat-history-item').forEach(item => {
                item.classList.remove('active');
            });

            chatHistoryContainer.prepend(historyItem); // Add to the top

            // Make sure the new session is marked as active
            historyItem.classList.add('active');

            updateSendButtonState();

        } catch (error) {
            console.error("Error creating new chat session:", error);
            showToast('Could not start a new session. Please check the server connection.', 'error');
        }
        finally{
            hideLoadingIndicator();
        }
    };

    const deleteCurrentChatSession = async () => {
        if (!currentSessionId) return;
        
        showConfirmationModal('Are you sure you want to delete this chat session?', async () => {
            showLoadingIndicator();
            try {
                const response = await fetch(`/api/sessions/${currentSessionId}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    throw new Error('Failed to delete session');
                }
                
                // Remove the session from UI
                const sessionElement = document.querySelector(`[data-session-id="${currentSessionId}"]`);
                if (sessionElement) {
                    sessionElement.remove();
                }
                
                // Find another session to switch to or create new one
                const remainingSessions = document.querySelectorAll('.chat-history-item');
                if (remainingSessions.length > 0) {
                    const firstSession = remainingSessions[0];
                    loadChat(firstSession.dataset.sessionId);
                } else {
                    createNewChatSession();
                }
                
            } catch (error) {
                console.error('Error deleting session:', error);
            }
            finally{
                hideLoadingIndicator();
            }
        });
    };
    
    // Initial load from localStorage

   const initialLoad = async () => {
        showLoadingIndicator();
        try {
            const response = await fetch('/api/initial-data');
            if (!response.ok) {
                throw new Error('Could not load initial chat data.');
            }
            const data = await response.json();

            // Populate the CSV file dropdown
            populateCsvDropdown(data.data_sources);
            
            // Clear and populate chat history sidebar
            const chatHistoryContainer = document.querySelector('.chat-history');
            chatHistoryContainer.innerHTML = '';
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(session => {
                    // Use the new helper function to create each element
                    const historyItem = createSessionElement(session);
                    chatHistoryContainer.appendChild(historyItem);
                });
            }
            
            // Load the most recent session, or create a new one
            if (data.active_session_id) {
                loadChat(data.active_session_id);
            } else {
                createNewChatSession();
            }

        } catch (error) {
            console.error("Error on initial load:", error);
            const chatMessages = document.querySelector('.chat-messages');
            chatMessages.innerHTML = `<div class="error-message">Could not connect to the server to load chat history. Please refresh the page.</div>`;
        }
        finally {
            hideLoadingIndicator();
        }
    };

    const populateCsvDropdown = (dataSources) => {
        csvFileSelector.innerHTML = '<option value="" disabled selected>Select a CSV file</option>';
        if (dataSources && dataSources.length > 0) {
            dataSources.forEach(source => {
                const option = document.createElement('option');
                option.value = source.id;
                option.textContent = source.filename;
                csvFileSelector.appendChild(option);
            });
        }
    };

    // --- END: Chat Session Management ---

    // --- START: Handle Sending Message and Bot Response ---

    function scrollToBottom() {
        const chatMessages = document.querySelector('.chat-messages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    const handleSendMessage = async () => {
        const userMessage = userInput.value.trim();
        
        // Check if current session is generating
        const sessionState = sessionLoadingStates.get(currentSessionId);
        if (!userMessage || (sessionState && sessionState.isGenerating)) return;

        const modelSelector = document.getElementById('model');
        const selectedModel = modelSelector.value;
        const selectedFileId = csvFileSelector.value;

        addMessageToChat('user', userMessage);
        userInput.value = '';
        updateSendButtonState();

        // Set up session loading state
        const abortController = new AbortController();
        sessionLoadingStates.set(currentSessionId, {
            isGenerating: true,
            abortController: abortController
        });

        // Update UI
        sendBtn.classList.add('button-hidden');
        stopBtn.classList.remove('button-hidden');
        updateSendButtonState();
        showAILoadingIndicator();

        const messageSessionId = currentSessionId; // Capture session ID

        const updateSessionTitle = () => {
            fetch(`/api/sessions/${messageSessionId}/title`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userMessage: userMessage })
            })
            .then(response => {
                if (!response.ok) throw new Error('Failed to fetch session title.');
                return response.json();
            })
            .then(data => {
                const sessionItem = document.querySelector(`.chat-history-item[data-session-id="${messageSessionId}"]`);
                if (sessionItem) {
                    sessionItem.textContent = data.title;
                    console.log(`Session title updated to: "${data.title}. Session Id: ${messageSessionId}`);
                }
            })
            .catch(err => console.error("Error updating session title:", err));
        };

        try {
            const response = await fetch(`/api/sessions/${messageSessionId}/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: abortController.signal,
                body: JSON.stringify({
                    message: userMessage,
                    data_source_id: selectedFileId,
                    model: selectedModel
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.response || errorData.error || 'A server error occurred.');
            }

            const botResponseData = await response.json();

            // Hide loading indicator if we're viewing this session
            if (currentSessionId === messageSessionId) {
                hideAILoadingIndicator();
            }

            // Add messages only if we're viewing this session
            if (currentSessionId === messageSessionId) {
                // 1. Add the text part of the response if it exists.
                if (botResponseData.text) {
                    addMessageToChat('bot', botResponseData.text);
                }

                // 2. Loop through the files array and add each one individually.
                if (botResponseData.files && botResponseData.files.length > 0) {
                    botResponseData.files.forEach(fileContent => {
                        addMessageToChat('bot', fileContent);
                    });
                }
                scrollToBottom();
            }

            // After a successful message, update the title
            updateSessionTitle();

        } catch (error) {
            // Hide loading indicator if we're viewing this session
            if (currentSessionId === messageSessionId) {
                hideAILoadingIndicator();
            }

            if (error.name === 'AbortError') {
                // Add message only if we're viewing this session
                if (currentSessionId === messageSessionId) {
                    addMessageToChat('bot', 'Response generation stopped.');
                }
                
                // Log the stop event
                fetch(`/api/sessions/${messageSessionId}/log-stop`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                })
                .then(response => {
                    if (!response.ok) throw new Error('Failed to log stop event.');
                    updateSessionTitle();
                })
                .catch(err => console.error("Error logging stop event:", err));
            } else {
                // Add error message only if we're viewing this session
                if (currentSessionId === messageSessionId) {
                    addMessageToChat('bot', "I'm sorry, an issue occurred. Please try again later.");
                }
                console.error('Error fetching bot response:', error);
                
                // Log the error
                fetch(`/api/sessions/${messageSessionId}/log-error`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ error: error.message })
                })
                .then(response => {
                    if (!response.ok) throw new Error('Failed to log error event.');
                    updateSessionTitle();
                })
                .catch(err => console.error("Error logging error event:", err));
            }
            
            // Scroll only if we're viewing this session
            if (currentSessionId === messageSessionId) {
                scrollToBottom();
            }
            
        } finally {
            // Clean up session loading state
            sessionLoadingStates.delete(messageSessionId);
            
            // Update UI only if we're viewing this session
            if (currentSessionId === messageSessionId) {
                stopBtn.classList.add('button-hidden');
                sendBtn.classList.remove('button-hidden');
                updateSendButtonState();
            }
        }
    };

    const sessionLoadingStates = new Map(); // sessionId -> { isGenerating: boolean, abortController: AbortController }

    // Function to show AI loading indicator - only shows if session is actually generating
    const showAILoadingIndicator = () => {
        const sessionState = sessionLoadingStates.get(currentSessionId);
        if (sessionState && sessionState.isGenerating) {
            let loadingIndicator = document.getElementById('loading-indicator');
            if (!loadingIndicator) {
                loadingIndicator = document.createElement('div');
                loadingIndicator.id = 'loading-indicator';
                loadingIndicator.className = 'loading-indicator';
                loadingIndicator.innerHTML = `
                    <div class="loading-dots">
                        <div class="loading-dot"></div>
                        <div class="loading-dot"></div>
                        <div class="loading-dot"></div>
                    </div>
                    <span class="loading-text">AI is thinking...</span>
                `;
                document.querySelector('.chat-area').appendChild(loadingIndicator);
            }
            
            // Show with animation
            setTimeout(() => {
                loadingIndicator.classList.add('show');
            }, 10);
        }
    };


    function hideAILoadingIndicator() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('show');
            setTimeout(() => {
                loadingIndicator.remove();
            }, 300);
        }
    }

    const handleStopGeneration = () => {
        console.log("ABORT");
        const sessionState = sessionLoadingStates.get(currentSessionId);
        if (sessionState && sessionState.abortController) {
            sessionState.abortController.abort();
        }
    };

   
    function showLoadingIndicator() {
        // The 'flex' display style comes from our CSS for centering
        document.getElementById('global-loading-overlay').style.display = 'flex';
    }

    function hideLoadingIndicator() {
        document.getElementById('global-loading-overlay').style.display = 'none';
    }

    // --- END: Handle Sending Message and Bot Response ---

    function showToast(message, type = 'error') {
        // Create the toast element
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.textContent = message;

        // Add it to the page
        document.body.appendChild(toast);

        // Remove the toast after 3 seconds
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    // Add this new function to bot.js
    function enableEditMode(sessionItem, titleSpan) {
        // Get original title and session ID
        const originalTitle = titleSpan.textContent;
        const sessionId = sessionItem.dataset.sessionId;

        // Hide the original title span
        titleSpan.style.display = 'none';
        
        // Create the editor input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'title-editor';
        input.value = originalTitle;
        
        // Create the action buttons container
        const editActions = document.createElement('div');
        editActions.className = 'edit-actions';

        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';
        saveBtn.className = 'save-title-btn';

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';

        editActions.append(cancelBtn, saveBtn);

        // Combine into a form to handle submission
        const editForm = document.createElement('form');
        editForm.append(input, editActions);
        sessionItem.prepend(editForm); // Add to the start of the item
        input.focus(); // Focus the input
        input.select(); // Select the text

        // --- Event Handlers ---
        const exitEditMode = () => {
            editForm.remove();
            titleSpan.style.display = 'block';
        };

        cancelBtn.onclick = exitEditMode;

        editForm.onsubmit = (e) => {
            e.preventDefault(); // Prevent default form submission
            const newTitle = input.value.trim();

            if (newTitle && newTitle !== originalTitle) {
                // Optimistically update the UI
                titleSpan.textContent = newTitle;
                
                // Call the backend to save the change
                fetch(`/api/sessions/${sessionId}/rename`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_title: newTitle })
                })
                .then(response => {
                    if (!response.ok) {
                        // If backend fails, revert the title in the UI
                        titleSpan.textContent = originalTitle;
                        alert('Error: Could not rename session.');
                    }
                });
            }
            exitEditMode();
        };
    }

    function createSessionElement(session) {
        const historyItem = document.createElement('div');
        historyItem.className = 'chat-history-item';
        historyItem.dataset.sessionId = session.id;

        // Create the title part
        const titleSpan = document.createElement('span');
        titleSpan.className = 'session-title';
        titleSpan.textContent = session.title;
        titleSpan.onclick = () => loadChat(session.id);

        // Create the actions part (3-dot button)
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'session-actions';

        const editButton = document.createElement('button');
        editButton.innerHTML = '&#8942;'; // Vertical ellipsis
        editButton.title = 'Rename session';
        editButton.onclick = (e) => {
            e.stopPropagation(); // Prevent the chat from loading
            enableEditMode(historyItem, titleSpan);
        };

        actionsDiv.appendChild(editButton);
        historyItem.append(titleSpan, actionsDiv);
        
        return historyItem;
    }


    // --- START: Event Listeners ---
    sidebarToggle.addEventListener('click', handleSidebarToggle);
    userInput.addEventListener('input', updateSendButtonState);
    csvFileSelector.addEventListener('change', updateSendButtonState);
    sendBtn.addEventListener('click', handleSendMessage);
    stopBtn.addEventListener('click', handleStopGeneration);
    newChatBtn.addEventListener('click', createNewChatSession);
    deleteChatBtn.addEventListener('click', deleteCurrentChatSession);
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendBtn.click();
        }
    });
    userInput.addEventListener('input', () => {
        // Temporarily reset height to allow it to shrink
        userInput.style.height = 'auto';
        
        // Set the height to match the content's full height
        userInput.style.height = `${userInput.scrollHeight}px`;

        // Show a scrollbar only if the content exceeds the max-height from CSS
        if (userInput.scrollHeight > parseInt(getComputedStyle(userInput).maxHeight)) {
            userInput.style.overflowY = 'auto';
        } else {
            userInput.style.overflowY = 'hidden';
        }
    });
    const exitBtnLink = document.querySelector('.exit-btn');
    if (exitBtnLink) {
        exitBtnLink.addEventListener('click', (event) => {
            hideAILoadingIndicator()
            event.preventDefault(); 
            showLoadingIndicator();
            requestAnimationFrame(() => {
                window.location.href = exitBtnLink.href;
            });
        });
    }
    // --- END: Event Listeners ---
    
    // --- START: Initial Page Load ---
    initialLoad();
    // --- END: Initial Page Load ---
});