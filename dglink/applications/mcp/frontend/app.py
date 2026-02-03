from flask import Flask, render_template, request, jsonify, Response
import requests
import json
import os

app = Flask(__name__)

# Backend API configuration - use environment variable for Docker, fallback to localhost
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        model_provider = data.get('provider', 'anthropic')  # 'anthropic' or 'openai'
        
        # Forward request to your backend
        response = requests.post(
            f'{BACKEND_URL}/chat',
            json={
                'message': user_message,
                'provider': model_provider
            },
            stream=True,
            timeout=300
        )
        
        # Stream the response back to the client
        def generate():
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk:
                    yield chunk
        
        return Response(generate(), mimetype='text/plain')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def get_health():
    """Get health status from backend"""
    try:
        response = requests.get(f'{BACKEND_URL}/health')
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)