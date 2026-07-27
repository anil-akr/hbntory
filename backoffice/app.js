document.addEventListener('DOMContentLoaded', () => {
    // 1. Récupération des éléments du DOM
    const sendBtn = document.getElementById('send-btn');
    const userQueryInput = document.getElementById('user-query');
    const chatHistory = document.getElementById('chat-history');

    // 2. Fonction principale d'envoi du message
    async function sendMessage() {
        const questionText = userQueryInput.value.trim();
        
        // On ne fait rien si le champ est vide
        if (!questionText) return;

        // Affiche la question de l'utilisateur
        chatHistory.innerHTML += `
            <div class="user-message">
                <strong>Vous :</strong><br>${escapeHTML(questionText)}
            </div>
        `;

        // Vide la zone de texte
        userQueryInput.value = '';

        // Affiche l'indicateur de chargement
        const loadingId = 'loading-' + Date.now();
        chatHistory.innerHTML += `<div id="${loadingId}" class="loading">Recherche en cours...</div>`;
        
        // Fait défiler le tchat vers le bas
        chatHistory.scrollTop = chatHistory.scrollHeight;

        try {
            // Envoi de la requête au serveur Flask
            const response = await fetch('http://127.0.0.1:8001/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: questionText })
            });

            const data = await response.json();

            // Retirer le message de chargement
            const loadingElement = document.getElementById(loadingId);
            if (loadingElement) loadingElement.remove();

            if (response.ok) {
                // Affiche la réponse de l'assistant
                chatHistory.innerHTML += `
                    <div class="ai-message">
                        <strong>Assistant :</strong><br>${data.answer}
                    </div>
                `;
            } else {
                // Affiche une erreur renvoyée par le serveur
                chatHistory.innerHTML += `
                    <div class="error">
                        ${data.error || 'Une erreur est survenue sur le serveur.'}
                    </div>
                `;
            }
        } catch (err) {
            // Retirer le message de chargement en cas d'erreur réseau
            const loadingElement = document.getElementById(loadingId);
            if (loadingElement) loadingElement.remove();

            chatHistory.innerHTML += `
                <div class="error">
                    Impossible de contacter le serveur Flask.
                </div>
            `;
        }

        // Fait défiler automatiquement vers le bas après la réponse
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // 3. Fonction de sécurité pour éviter l'injection de code HTML
    function escapeHTML(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 4. Écouteur pour le clic sur le bouton Envoyer
    sendBtn.addEventListener('click', sendMessage);

    // 5. Écouteur pour la touche Entrée
    userQueryInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
});