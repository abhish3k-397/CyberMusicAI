document.addEventListener('DOMContentLoaded', function() {
    const chatHistory = document.getElementById('chat-history');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const newChatBtn = document.getElementById('new-chat-btn');

    // Add Spotify login button
    const spotifyLoginBtn = document.createElement('button');
    spotifyLoginBtn.innerHTML = '<i class="fab fa-spotify"></i> CONNECT SPOTIFY';
    spotifyLoginBtn.classList.add('cyber-button', 'spotify-button');
    spotifyLoginBtn.id = 'spotify-login-btn';
    spotifyLoginBtn.addEventListener('click', () => {
        window.location.href = '/login';
    });
    document.querySelector('.header-buttons').prepend(spotifyLoginBtn);

    // Check if we have a Spotify token
    function checkSpotifyStatus() {
        fetch('/check_spotify')
            .then(response => response.json())
            .then(data => {
                if (data.authenticated) {
                    spotifyLoginBtn.innerHTML = '<i class="fab fa-spotify"></i> SPOTIFY CONNECTED';
                    spotifyLoginBtn.style.backgroundColor = '#1DB954';
                }
            })
            .catch(error => console.error('Error checking Spotify status:', error));
    }

    // Call this on page load
    checkSpotifyStatus();

    // Add cyberpunk message effect
    function addMessage(content, isUser) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', isUser ? 'user-message' : 'bot-message');
        
        if (!isUser) {
            messageDiv.innerHTML = `<span class="typing-indicator"></span>`;
            setTimeout(() => {
                // Check if content is HTML or plain text
                if (content.startsWith('<') && content.endsWith('>')) {
                    messageDiv.innerHTML = content;
                } else {
                    messageDiv.innerHTML = markdownToHtml(content);
                }
                typewriterEffect(messageDiv);
            }, 1000);
        } else {
            messageDiv.textContent = content;
        }
        
        chatHistory.appendChild(messageDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Enhanced typewriter effect that preserves HTML
    function typewriterEffect(element) {
        const originalHtml = element.innerHTML;
        element.innerHTML = '';
        let i = 0;
        const speed = 20 + Math.random() * 30;
        let tagBuffer = '';
        let insideTag = false;

        function type() {
            if (i < originalHtml.length) {
                const char = originalHtml.charAt(i);
                
                // Handle HTML tags
                if (char === '<') {
                    insideTag = true;
                    tagBuffer = char;
                } else if (char === '>' && insideTag) {
                    tagBuffer += char;
                    element.innerHTML += tagBuffer;
                    tagBuffer = '';
                    insideTag = false;
                    i++;
                    setTimeout(type, speed);
                    return;
                } else if (insideTag) {
                    tagBuffer += char;
                    i++;
                    setTimeout(type, speed);
                    return;
                }
                
                // Regular characters
                if (!insideTag) {
                    element.innerHTML += char;
                }
                
                i++;
                setTimeout(type, speed);
            }
        }
        type();
    }

    // Complete markdown to HTML converter
    function markdownToHtml(text) {
        // Bold (**text**)
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Italic (*text* or _text_)
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
        text = text.replace(/_(.*?)_/g, '<em>$1</em>');
        
        // Bullet points
        text = text.replace(/^\s*[-*+]\s+(.+)/gm, '<li>$1</li>');
        if (/<li>/.test(text)) {
            text = text.replace(/(<li>.*<\/li>)/gms, '<ul>$1</ul>');
        }
        
        // Tables (basic support)
        text = text.replace(/^\|(.+?)\|(.+?)\|$/gm, '<tr><td>$1</td><td>$2</td></tr>');
        if (/<tr>/.test(text)) {
            text = '<table>' + text + '</table>';
        }
        
        return text;
    }

    // Play song on Spotify
    async function playOnSpotify(songName, artistName = '') {
        try {
            const response = await fetch('/play_song', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    song_name: songName,
                    artist_name: artistName 
                })
            });
            
            const data = await response.json();
            if (data.error) {
                return `<div class="spotify-error">${data.error}</div>`;
            } else {
                return `
                    <div class="spotify-player">
                        <div class="track-info">
                            <img src="${data.album_cover}" alt="Album Cover" class="album-cover">
                            <div class="track-details">
                                <div class="track-name">${data.track}</div>
                                <div class="artist-name">${data.artist}</div>
                            </div>
                        </div>
                        ${data.preview_url ? `
                        <audio controls class="audio-preview">
                            <source src="${data.preview_url}" type="audio/mpeg">
                            Your browser does not support the audio element.
                        </audio>
                        ` : ''}
                        <a href="${data.external_url}" target="_blank" class="spotify-link">
                            <i class="fab fa-spotify"></i> Open in Spotify
                        </a>
                    </div>
                `;
            }
        } catch (error) {
            return `<div class="spotify-error">Failed to connect to Spotify</div>`;
        }
    }

    // Send message to backend
    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        addMessage(message, true);
        userInput.value = '';
        
        // Check if it's a play command
        const playRegex = /^(play|listen to)\s+(.+)/i;
        const playMatch = message.match(playRegex);
        
        if (playMatch && playMatch[2]) {
            const songQuery = playMatch[2];
            const spotifyResponse = await playOnSpotify(songQuery);
            addMessage(spotifyResponse, false);
            return;
        }
        
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            });
            
            const data = await response.json();
            if (data.error) {
                addMessage(`SYSTEM ERROR: ${data.error}`, false);
            } else {
                // Check if this is a play command response from Gemini
                if (data.play_command) {
                    const { song_name, artist_name } = data.play_command;
                    const spotifyResponse = await playOnSpotify(song_name, artist_name);
                    addMessage(markdownToHtml(data.response) + spotifyResponse, false);
                } else {
                    addMessage(data.response, false);
                }
            }
        } catch (error) {
            addMessage("NETWORK CONNECTION FAILED", false);
        }
    }

    // New chat function
    async function newChat() {
        try {
            const response = await fetch('/reset_session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (response.ok) {
                chatHistory.innerHTML = '';
                addMessage("SYSTEM REBOOTED. READY FOR MUSIC QUERIES.", false);
                userInput.focus();
            } else {
                addMessage("SYSTEM ERROR: Failed to reset session", false);
            }
        } catch (error) {
            addMessage("NETWORK ERROR: Could not reset session", false);
        }
    }

    // Voice input button
    const voiceBtn = document.createElement('button');
    voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
    voiceBtn.classList.add('cyber-button', 'voice-button');
    voiceBtn.addEventListener('click', () => {
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = 'en-US';
        recognition.onresult = (event) => {
            userInput.value = event.results[0][0].transcript;
        };
        recognition.start();
    });
    document.querySelector('.cyber-input-area').prepend(voiceBtn);

    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    newChatBtn.addEventListener('click', newChat);

    // Initial welcome message
    setTimeout(() => {
        addMessage("SYSTEM INITIALIZED. READY FOR MUSIC QUERIES.", false);
    }, 500);
});