from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import google.generativeai as genai
from uuid import uuid4
import requests
from urllib.parse import urlencode
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "some_random_secret_key")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = "http://localhost:5000/callback"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

# Configure Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY")) 
model = genai.GenerativeModel('gemini-2.0-flash')

# Global store for chat sessions
chat_sessions = {}

system_instruction = """
You are a specialized AI assistant that only responds to music-related questions. 
From this point forward, you must ignore or politely decline to answer any question that is not related to music. 
This includes topics outside of music such as history, science, personal advice, politics, or general knowledge. 
If a user asks a non-music-related question, respond with:
'Sorry, I can only answer music-related questions. Please ask something about music!'
Stay in this mode permanently until the session has ended. 
Do check if I have entered the spelling wrong or something and it is related to music, and also do reply to greetings. 
You have to remember everything I have asked about before as well. Also if i ask about someone or something do verify if it has any relation to music before answering. When i ask for links from Spotify provide it whatever it is.

When users ask to play a song, respond with:
'Playing [song name] by [artist] on Spotify...'
but don't include any markdown or special formatting.
"""

@app.route('/')
def home():
    # Assign a unique session ID if not already assigned
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
    return render_template('index.html')

@app.route('/login')
def login():
    """Redirect to Spotify authorization page"""
    scope = 'user-read-playback-state user-modify-playback-state'
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'scope': scope,
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle Spotify callback and get access token"""
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})
    
    if 'code' in request.args:
        code = request.args['code']
        payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': SPOTIFY_REDIRECT_URI,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET,
        }
        response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
        if response.status_code == 200:
            token_info = response.json()
            session['spotify_token'] = token_info['access_token']
            session['spotify_refresh_token'] = token_info.get('refresh_token')
            session['spotify_token_expires'] = time.time() + token_info['expires_in']
            return redirect(url_for('home'))
        return jsonify({"error": "Failed to get access token"})
    return redirect(url_for('home'))

def refresh_spotify_token():
    """Refresh Spotify access token if expired"""
    if 'spotify_refresh_token' not in session:
        return False
    
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': session['spotify_refresh_token'],
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
    }
    response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
    if response.status_code == 200:
        token_info = response.json()
        session['spotify_token'] = token_info['access_token']
        session['spotify_token_expires'] = time.time() + token_info['expires_in']
        return True
    return False

def get_spotify_headers():
    """Get headers with current access token"""
    if 'spotify_token' not in session:
        return None
    
    # Refresh token if expired
    if time.time() > session.get('spotify_token_expires', 0):
        if not refresh_spotify_token():
            return None
    
    return {
        'Authorization': f"Bearer {session['spotify_token']}",
        'Content-Type': 'application/json',
    }

@app.route('/play_song', methods=['POST'])
def play_song():
    """Play a song on Spotify"""
    if 'spotify_token' not in session:
        return jsonify({"error": "Not authenticated with Spotify"})
    
    data = request.json
    song_name = data.get('song_name')
    artist_name = data.get('artist_name', '')
    
    # Search for the track
    headers = get_spotify_headers()
    if not headers:
        return jsonify({"error": "Spotify authentication failed"})
    
    search_url = f"{SPOTIFY_API_BASE_URL}/search"
    params = {
        'q': f'track:"{song_name}" artist:"{artist_name}"',
        'type': 'track',
        'limit': 1
    }



    
    # response = requests.get(search_url, headers=headers, params=params)
    # if response.status_code != 200:
    #     return jsonify({"error": "Failed to search for track"})
    
    response = requests.get(search_url, headers=headers, params=params)

    # ADD THIS FOR DEBUGGING
    print("Search URL:", response.url)
    print("Status Code:", response.status_code)
    print("Response Text:", response.text)

    if response.status_code != 200:
        return jsonify({"error": "Failed to search for track"})
    
    tracks = response.json().get('tracks', {}).get('items', [])
    if not tracks:
        return jsonify({"error": "Track not found"})
    
    track_uri = tracks[0]['uri']
    
    # Play the track
    play_url = f"{SPOTIFY_API_BASE_URL}/me/player/play"
    play_response = requests.put(play_url, headers=headers, json={'uris': [track_uri]})
    
    if play_response.status_code == 204:
        return jsonify({
            "status": "success",
            "track": tracks[0]['name'],
            "artist": ", ".join([a['name'] for a in tracks[0]['artists']]),
            "preview_url": tracks[0]['preview_url'],
            "external_url": tracks[0]['external_urls']['spotify'],
            "album_cover": tracks[0]['album']['images'][0]['url'] if tracks[0]['album']['images'] else None
        })
    return jsonify({"error": "Failed to play track"})

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json['message']
    session_id = session.get('session_id')

    if session_id not in chat_sessions:
        # Create a new chat only once for the session
        chat_sessions[session_id] = model.start_chat(history=[
            {"role": "user", "parts": [system_instruction]},
            {"role": "model", "parts": ["Understood! I'm ready for music questions."]}
        ])
    
    try:
        chat = chat_sessions[session_id]
        response = chat.send_message(user_input)
        
        # Check if the response indicates a play command
        if "Playing" in response.text and "on Spotify" in response.text:
            # Extract song name from the response
            parts = response.text.split("Playing")[1].split("on Spotify")[0].strip()
            song_parts = parts.split(" by ")
            song_name = song_parts[0].strip()
            artist_name = song_parts[1].strip() if len(song_parts) > 1 else ""
            
            # Return both the text response and play command
            return jsonify({
                "response": response.text,
                "play_command": {
                    "song_name": song_name,
                    "artist_name": artist_name
                }
            })
        
        return jsonify({"response": response.text})
    
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/reset_session', methods=['POST'])
def reset_session():
    session_id = session.get('session_id')
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    # Generate a new session ID
    session['session_id'] = str(uuid4())
    return jsonify({"status": "success"})
@app.route('/check_spotify')
def check_spotify():
    """Check if user is authenticated with Spotify"""
    return jsonify({
        "authenticated": 'spotify_token' in session and 
                         time.time() < session.get('spotify_token_expires', 0)
    })
if __name__ == '__main__':
    app.run(debug=True)