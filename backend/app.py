from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import datetime
import json
import time
import os
import threading
from contextlib import contextmanager
from video_processor import SimpleVideoToText

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# Database configuration
DB_PATH = 'database.db'
DB_TIMEOUT = 30  # 30 seconds timeout

# Thread-local storage for database connections
thread_local = threading.local()

@contextmanager
def get_db_connection():
    """Context manager for database connections with proper error handling and timeouts"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA busy_timeout=30000;')  # 30 seconds
        conn.execute('PRAGMA synchronous=NORMAL;')
        yield conn
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# Initialize database
def init_db():
    """Initialize database with proper error handling"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS video_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    video_url TEXT NOT NULL,
                    video_title TEXT,
                    transcript TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            conn.commit()
            print("✅ Database initialized successfully")
    except sqlite3.Error as e:
        print(f"❌ Database initialization failed: {e}")
        raise e

# Helper functions
def get_user_by_token(token):
    """Get user ID from JWT token"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

@app.route('/register', methods=['POST'])
def register():
    """User registration endpoint with improved error handling"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        # Validation
        if not username or not email or not password:
            return jsonify({'error': 'All fields are required'}), 400
            
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
            
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Hash password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                          (username, email, hashed))
            conn.commit()
            
        return jsonify({'message': 'User created successfully'}), 201
        
    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            return jsonify({'error': 'Username already exists'}), 400
        elif 'email' in str(e):
            return jsonify({'error': 'Email already exists'}), 400
        else:
            return jsonify({'error': 'User already exists'}), 400
    except sqlite3.Error as e:
        print(f"Database error in register: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Unexpected error in register: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/login', methods=['POST'])
def login():
    """User login endpoint with improved error handling"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, password FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            token = jwt.encode({
                'user_id': user['id'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({'token': token, 'message': 'Login successful'}), 200
        
        return jsonify({'error': 'Invalid username or password'}), 401
        
    except sqlite3.Error as e:
        print(f"Database error in login: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Unexpected error in login: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/process-video', methods=['POST'])
def process_video():
    """Standard video processing endpoint"""
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    user_id = get_user_by_token(token.replace('Bearer ', ''))
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        video_url = data.get('video_url', '').strip()
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        
        # Process video
        converter = SimpleVideoToText()
        transcript, summary = converter.process_video(video_url)
        video_title, _ = converter.get_video_info(video_url)
        
        if transcript and summary:
            # Save to database
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO video_jobs (user_id, video_url, video_title, transcript, summary)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, video_url, video_title, transcript, summary))
                conn.commit()
            
            return jsonify({
                'message': 'Video processed successfully',
                'video_title': video_title,
                'transcript': transcript,
                'summary': summary
            }), 200
        else:
            return jsonify({'error': 'Failed to process video'}), 500
            
    except sqlite3.Error as e:
        print(f"Database error in process_video: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error processing video: {e}")
        return jsonify({'error': f'Video processing failed: {str(e)}'}), 500

@app.route('/process-video-stream', methods=['POST'])
def process_video_stream():
    """Real-time streaming video processing endpoint"""
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    user_id = get_user_by_token(token.replace('Bearer ', ''))
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
        
    video_url = data.get('video_url', '').strip()
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400

    def generate():
        audio_file = None
        try:
            # Send initial status
            yield f"data: {json.dumps({'type': 'status', 'message': 'Starting video processing...'})}\n\n"
            
            converter = SimpleVideoToText()
            
            # Get video info
            yield f"data: {json.dumps({'type': 'status', 'message': 'Getting video information...'})}\n\n"
            video_title, video_id = converter.get_video_info(video_url)
            
            yield f"data: {json.dumps({'type': 'status', 'message': f'Found video: {video_title}'})}\n\n"
            
            # Download audio
            yield f"data: {json.dumps({'type': 'status', 'message': 'Downloading audio...'})}\n\n"
            audio_file = converter.download_audio(video_url)
            
            # Transcribe
            yield f"data: {json.dumps({'type': 'status', 'message': 'Transcribing audio to text...'})}\n\n"
            transcript = converter.transcribe_audio(audio_file)
            
            yield f"data: {json.dumps({'type': 'transcript', 'data': transcript})}\n\n"
            
            # Generate summary with streaming
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating AI summary... (Live typing)'})}\n\n"
            
            prompt = f"""
            Please create a comprehensive summary of the following video transcript. 
            The summary should be medium to large in length, covering all main points, key insights, and important details discussed in the video.
            Make it informative and well-structured with clear sections where appropriate.
            Include any important quotes, statistics, or examples mentioned.

            Transcript:
            {transcript}

            Summary:
            """
            
            # Stream the LLM response
            summary = ""
            try:
                for chunk in converter.llm.stream(prompt):
                    summary += chunk
                    yield f"data: {json.dumps({'type': 'summary_chunk', 'data': chunk})}\n\n"
                    time.sleep(0.03)  # Small delay for realistic typing effect
            except Exception as e:
                # Fallback to regular generation if streaming fails
                yield f"data: {json.dumps({'type': 'status', 'message': 'Streaming failed, generating complete summary...'})}\n\n"
                summary = converter.generate_summary(transcript)
                yield f"data: {json.dumps({'type': 'summary_chunk', 'data': summary})}\n\n"
            
            # Save to database
            yield f"data: {json.dumps({'type': 'status', 'message': 'Saving to database...'})}\n\n"
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO video_jobs (user_id, video_url, video_title, transcript, summary)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, video_url, video_title, transcript, summary))
                conn.commit()
            
            yield f"data: {json.dumps({'type': 'complete', 'video_title': video_title, 'message': 'Processing completed successfully!'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Clean up temporary audio file
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except:
                    pass
            
            # Clean up any remaining temp files
            try:
                for file in os.listdir('.'):
                    if file.startswith('temp_audio'):
                        os.remove(file)
            except:
                pass
    
    return Response(generate(), 
                   mimetype='text/plain',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive'})

@app.route('/my-videos', methods=['GET'])
def get_user_videos():
    """Get user's video history"""
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    user_id = get_user_by_token(token.replace('Bearer ', ''))
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT video_title, transcript, summary, created_at 
                FROM video_jobs WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            videos = cursor.fetchall()
        
        result = []
        for video in videos:
            result.append({
                'title': video['video_title'],
                'transcript': video['transcript'],
                'summary': video['summary'],
                'date': video['created_at']
            })
        
        return jsonify({'videos': result}), 200
        
    except sqlite3.Error as e:
        print(f"Database error in get_user_videos: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error getting user videos: {e}")
        return jsonify({'error': 'Failed to retrieve videos'}), 500

@app.route('/admin/stats', methods=['GET'])
def get_stats():
    """Get basic statistics"""
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    user_id = get_user_by_token(token.replace('Bearer ', ''))
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get total users
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # Get total videos
            cursor.execute('SELECT COUNT(*) FROM video_jobs')
            total_videos = cursor.fetchone()[0]
            
            # Get videos processed today
            cursor.execute('SELECT COUNT(*) FROM video_jobs WHERE DATE(created_at) = DATE("now")')
            videos_today = cursor.fetchone()[0]
            
            # Get current user's video count
            cursor.execute('SELECT COUNT(*) FROM video_jobs WHERE user_id = ?', (user_id,))
            user_videos = cursor.fetchone()[0]
            
            # Get processing time stats
            cursor.execute('SELECT AVG(LENGTH(transcript)), AVG(LENGTH(summary)) FROM video_jobs WHERE transcript IS NOT NULL')
            avg_stats = cursor.fetchone()
        
        return jsonify({
            'total_users': total_users,
            'total_videos': total_videos,
            'videos_today': videos_today,
            'user_videos': user_videos,
            'avg_transcript_length': int(avg_stats[0] or 0),
            'avg_summary_length': int(avg_stats[1] or 0),
            'models': {
                'speech_model': 'facebook/wav2vec2-base-960h (Wav2Vec2)',
                'summary_model': 'llama3.2 (Ollama Local)'
            }
        }), 200
        
    except sqlite3.Error as e:
        print(f"Database error in get_stats: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': 'Failed to retrieve statistics'}), 500

@app.route('/admin/detailed-stats', methods=['GET'])
def get_detailed_stats():
    """Get detailed statistics and analytics"""
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    user_id = get_user_by_token(token.replace('Bearer ', ''))
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get all users with their video counts
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.created_at,
                       COUNT(vj.id) as video_count,
                       MAX(vj.created_at) as last_video_date
                FROM users u
                LEFT JOIN video_jobs vj ON u.id = vj.user_id
                GROUP BY u.id, u.username, u.email, u.created_at
                ORDER BY u.created_at DESC
            ''')
            users = cursor.fetchall()
            
            # Get all videos with user info
            cursor.execute('''
                SELECT vj.id, vj.video_title, vj.video_url, vj.created_at,
                       u.username, u.email,
                       LENGTH(vj.transcript) as transcript_length,
                       LENGTH(vj.summary) as summary_length
                FROM video_jobs vj
                JOIN users u ON vj.user_id = u.id
                ORDER BY vj.created_at DESC
                LIMIT 100
            ''')
            videos = cursor.fetchall()
            
            # Get comprehensive stats
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT vj.user_id) as active_users,
                    COUNT(vj.id) as total_videos,
                    AVG(LENGTH(vj.transcript)) as avg_transcript_length,
                    AVG(LENGTH(vj.summary)) as avg_summary_length,
                    MIN(vj.created_at) as first_video_date,
                    MAX(vj.created_at) as latest_video_date,
                    COUNT(CASE WHEN DATE(vj.created_at) = DATE('now') THEN 1 END) as videos_today,
                    COUNT(CASE WHEN DATE(vj.created_at) >= DATE('now', '-7 days') THEN 1 END) as videos_this_week
                FROM video_jobs vj
            ''')
            comprehensive_stats = cursor.fetchone()
            
            # Get daily video counts for last 7 days
            cursor.execute('''
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM video_jobs 
                WHERE DATE(created_at) >= DATE('now', '-7 days')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            ''')
            daily_stats = cursor.fetchall()
        
        return jsonify({
            'users': [
                {
                    'id': user['id'],
                    'username': user['username'], 
                    'email': user['email'],
                    'created_at': user['created_at'],
                    'video_count': user['video_count'],
                    'last_video_date': user['last_video_date']
                } for user in users
            ],
            'videos': [
                {
                    'id': video['id'],
                    'title': video['video_title'],
                    'url': video['video_url'],
                    'created_at': video['created_at'],
                    'username': video['username'],
                    'user_email': video['email'],
                    'transcript_length': video['transcript_length'] or 0,
                    'summary_length': video['summary_length'] or 0
                } for video in videos
            ],
            'stats': {
                'active_users': comprehensive_stats['active_users'] or 0,
                'total_videos': comprehensive_stats['total_videos'] or 0,
                'avg_transcript_length': int(comprehensive_stats['avg_transcript_length'] or 0),
                'avg_summary_length': int(comprehensive_stats['avg_summary_length'] or 0),
                'first_video_date': comprehensive_stats['first_video_date'],
                'latest_video_date': comprehensive_stats['latest_video_date'],
                'videos_today': comprehensive_stats['videos_today'] or 0,
                'videos_this_week': comprehensive_stats['videos_this_week'] or 0
            },
            'daily_stats': [
                {
                    'date': day['date'],
                    'count': day['count']
                } for day in daily_stats
            ],
            'models': {
                'speech_recognition': 'facebook/wav2vec2-base-960h',
                'text_summarization': 'llama3.2 (Ollama)',
                'framework': 'HuggingFace Transformers + Ollama'
            }
        }), 200
        
    except sqlite3.Error as e:
        print(f"Database error in get_detailed_stats: {e}")
        return jsonify({'error': 'Database error occurred'}), 500
    except Exception as e:
        print(f"Error getting detailed stats: {e}")
        return jsonify({'error': 'Failed to retrieve detailed statistics'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'version': '1.0.0',
            'database': 'connected'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'version': '1.0.0',
            'database': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("🚀 Initializing Video to Text API Server")
    print("=" * 50)
    
    try:
        init_db()
        print("🌐 Server starting on http://localhost:5000")
        print("📊 Endpoints available:")
        print("   • POST /register - User registration")
        print("   • POST /login - User authentication") 
        print("   • POST /process-video - Standard video processing")
        print("   • POST /process-video-stream - Real-time streaming")
        print("   • GET /my-videos - User's video history")
        print("   • GET /admin/stats - Basic statistics")
        print("   • GET /admin/detailed-stats - Detailed analytics")
        print("   • GET /health - Health check")
        print("=" * 50)
        app.run(debug=True, port=5000, threaded=True)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        exit(1)