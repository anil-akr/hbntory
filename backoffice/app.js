document.addEventListener('DOMContentLoaded', () => {
    // 1. Grab the DOM elements
    const sendBtn = document.getElementById('send-btn');
    const userQueryInput = document.getElementById('user-query');
    const chatHistory = document.getElementById('chat-history');

    const AI_SERVICE_URL = 'http://127.0.0.1:8001/ask';

    // 2. Add one message to the conversation.
    //    The text is inserted with textContent, never as HTML: a question or an
    //    answer can therefore never be interpreted as markup. The CSS keeps the
    //    line breaks of the answer (white-space: pre-wrap).
    function appendMessage(cssClass, label, text) {
        const messageElement = document.createElement('div');
        messageElement.className = cssClass;

        if (label) {
            const labelElement = document.createElement('strong');
            labelElement.textContent = label;
            messageElement.appendChild(labelElement);
            messageElement.appendChild(document.createElement('br'));
        }

        messageElement.appendChild(document.createTextNode(text));
        chatHistory.appendChild(messageElement);

        // Always keep the latest message visible
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return messageElement;
    }

    // 3. Main function: send the question and display the answer
    async function sendMessage() {
        const questionText = userQueryInput.value.trim();

        // Do nothing when the field is empty
        if (!questionText) return;

        appendMessage('user-message', 'Vous :', questionText);
        userQueryInput.value = '';

        // Waiting feedback, removed as soon as the answer (or the error) is in.
        // The button is disabled meanwhile, so one question cannot be sent twice.
        const loadingElement = appendMessage('loading', '', 'Recherche en cours...');
        sendBtn.disabled = true;

        try {
            const response = await fetch(AI_SERVICE_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: questionText })
            });

            const data = await response.json();
            loadingElement.remove();

            if (response.ok) {
                appendMessage('ai-message', 'Assistant :', data.answer);
            } else {
                // Error returned by the service (for example the agent is down)
                appendMessage('error', '', data.error || 'Une erreur est survenue sur le serveur.');
            }
        } catch (err) {
            // Network error, or the AI service is not running
            loadingElement.remove();
            appendMessage('error', '', "Impossible de contacter le service IA (port 8001).");
        } finally {
            sendBtn.disabled = false;
        }
    }

    // 4. Listener for the Send button
    sendBtn.addEventListener('click', sendMessage);

    // 5. Listener for the Enter key
    userQueryInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
});
