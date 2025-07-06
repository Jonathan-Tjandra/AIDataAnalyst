import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_cors import CORS
import os
import random
import smtplib
import ssl
from email.message import EmailMessage
import time
from werkzeug.security import generate_password_hash, check_password_hash
import re
import requests
from werkzeug.utils import secure_filename

from google.oauth2 import id_token
from google.auth.transport import requests as google_auth_requests

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func as sqlalchemy_func

import boto3
from botocore.exceptions import ClientError
import uuid
from functools import wraps
import sys
import subprocess

import threading
from dotenv import load_dotenv
load_dotenv()

############## SETUP DB, CLOUDFARE ##################################################################################

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_super_secret_key_default_fallback_change_me')
app.config.update(
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE=True
)
CORS(app, supports_credentials=True)

R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL') # The public URL of bucket

s3_client = boto3.client(
    's3',
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name='auto' # R2 specific setting
)

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Important: Remove the query parameters from the URL itself
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split('?')[0]

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'sslmode': 'require'
        },
        'pool_pre_ping': True
    }

db = SQLAlchemy(app)

# Create connection pool for better performance
connection_pool = None

def get_db_connection():
    """Get a connection from the pool"""
    if connection_pool:
        return connection_pool.getconn()
    else:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def return_db_connection(conn):
    """Return a connection to the pool"""
    if connection_pool:
        connection_pool.putconn(conn)
    else:
        conn.close()

# --- Database Initialization ---
# This command creates all the tables defined above if they don't exist.
with app.app_context():
    db.create_all()
    print("SQLAlchemy database initialized successfully.")

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    
    # Relationships
    chat_sessions = db.relationship('ChatSession', backref='user', lazy=True, cascade="all, delete-orphan")
    data_sources = db.relationship('DataSource', backref='owner', lazy=True, cascade="all, delete-orphan")

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    session_title = db.Column(db.String(200), nullable=False)
    
    title_updated = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, server_default=sqlalchemy_func.now())
    updated_at = db.Column(db.DateTime, server_default=sqlalchemy_func.now(), onupdate=sqlalchemy_func.now())
    
    # Relationships
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade="all, delete-orphan")
    generated_files = db.relationship('GeneratedFile', backref='session', lazy=True, cascade="all, delete-orphan")

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    message_type = db.Column(db.String(10), nullable=False)  # 'user' or 'bot'
    message_content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=sqlalchemy_func.now())
    is_stopped = db.Column(db.Boolean, nullable=False, default=False)
    is_file_info = db.Column(db.Boolean, nullable=False, default=False)

class DataSource(db.Model):
    __tablename__ = 'data_sources'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(1024), nullable=False, unique=True) # Path in cloud storage
    file_type = db.Column(db.String(50), nullable=False, default='csv') # e.g., 'csv', 'gsheet'
    created_at = db.Column(db.DateTime, server_default=sqlalchemy_func.now())

class GeneratedFile(db.Model):
    __tablename__ = 'generated_files'
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    message_index = db.Column(db.Integer, nullable=True)  # Index of the message in the session
    original_prompt = db.Column(db.Text, nullable=False) # The user prompt that created the file
    file_type = db.Column(db.String(50), nullable=False) # e.g., 'png', 'csv'
    storage_path = db.Column(db.String(1024), nullable=False)  # REMOVED unique=True constraint
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)  # For soft delete
    created_at = db.Column(db.DateTime, server_default=sqlalchemy_func.now())
    intro_message = db.Column(db.Text, nullable=True)


############## END SETUP DB, CLOUDFARE ##################################################################################

################################### BOT UI HANDLING ####################################################################

@app.route('/bot')
def bot_page():
    # This tells Flask to find 'bot.html' in your 'templates' folder 
    # and send it to the user's browser.
    return render_template('bot.html')

############## HELPER FUNCTIONS #################################################################################

def login_required(f):
    """
    Decorator to ensure a user is logged in before accessing a route.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def _clean_stopped_messages(messages, s3_client):
    """
    Finds and deletes messages/files around a "stopped" event from the DB and R2.
    Returns True if deletions occurred, otherwise False.
    """
    indices_to_delete,  stop_indices = set(), set()

    # 1. Identify all messages that need to be deleted
    for i, msg in enumerate(messages):
        if msg.is_stopped:
            start_index = next((j for j in range(i - 1, -1, -1) if messages[j].message_type == 'user'), -1)
            end_index = next((j for j in range(i + 1, len(messages)) if messages[j].message_type == 'user'), len(messages))
            indices_to_delete.update(range(start_index + 1, end_index))
            stop_indices.add(i)

    indices_to_delete = indices_to_delete - stop_indices

    if indices_to_delete:
        messages_to_delete = [messages[i] for i in sorted(list(indices_to_delete), reverse=True)]
        # 2. Delete associated files from R2 and records from the database
        for msg_to_delete in messages_to_delete:
            if msg_to_delete.is_file_info:
                try:
                    file_id = int(msg_to_delete.message_content)
                    gen_file = GeneratedFile.query.get(file_id)
                    if gen_file:
                        db.session.delete(gen_file)
                        s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=gen_file.storage_path)
                except Exception as e:
                    print(f"Could not process/delete file for message {msg_to_delete.id}: {e}")
            db.session.delete(msg_to_delete)
        # 3. Commit all deletions
        db.session.commit()
    return indices_to_delete

def cleanup_db_orphans():
    """Deletes ChatMessage and GeneratedFile records not linked to any ChatSession."""
    from ui import db, ChatSession, ChatMessage, GeneratedFile
    print("--- Starting Database Cleanup ---")
    
    # Find and delete orphaned ChatMessages
    orphaned_messages = db.session.query(ChatMessage).outerjoin(ChatSession).filter(ChatSession.id == None).all()
    if orphaned_messages:
        print(f"Found {len(orphaned_messages)} orphaned chat messages to delete.")
        for msg in orphaned_messages:
            db.session.delete(msg)
    else:
        print("No orphaned chat messages found.")

    # Find and delete orphaned GeneratedFiles
    orphaned_files = db.session.query(GeneratedFile).outerjoin(ChatSession).filter(ChatSession.id == None).all()
    if orphaned_files:
        print(f"Found {len(orphaned_files)} orphaned file records to delete.")
        for file_record in orphaned_files:
            db.session.delete(file_record)
    else:
        print("No orphaned file records found.")
        
    if orphaned_messages or orphaned_files:
        db.session.commit()
        print("Database cleanup complete. Changes have been committed.")
    
    print("--- Finished Database Cleanup ---\n")


def cleanup_r2_orphans():
    """Deletes files from Cloudflare R2 that are not in the GeneratedFile table."""
    from ui import db, GeneratedFile
    print("--- Starting Cloudflare R2 Cleanup ---")
    
    # 1. Get all file paths from the database
    db_files_query = db.session.query(GeneratedFile.storage_path).filter(GeneratedFile.storage_path.isnot(None))
    db_file_paths = {row.storage_path for row in db_files_query}
    print(f"Found {len(db_file_paths)} valid file paths in the database.")

    # 2. Get all file paths from Cloudflare R2
    r2_file_paths = set()
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=R2_BUCKET_NAME, Prefix='generated/')
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                r2_file_paths.add(obj['Key'])
    print(f"Found {len(r2_file_paths)} files in Cloudflare R2 'generated/' folder.")

    # 3. Determine which files are orphaned
    orphaned_keys = r2_file_paths - db_file_paths
    
    if not orphaned_keys:
        print("No orphaned files found in Cloudflare R2.")
        print("--- Finished Cloudflare R2 Cleanup ---")
        return

    print(f"Found {len(orphaned_keys)} orphaned files to delete from Cloudflare R2.")
    
    # 4. Delete orphaned files in batches of up to 1000
    keys_to_delete = [{'Key': key} for key in orphaned_keys]
    for i in range(0, len(keys_to_delete), 1000):
        batch = keys_to_delete[i:i+1000]
        print(f"Deleting batch of {len(batch)} files...")
        s3_client.delete_objects(
            Bucket=R2_BUCKET_NAME,
            Delete={'Objects': batch}
        )

    print(f"Successfully deleted {len(orphaned_keys)} orphaned files.")
    print("--- Finished Cloudflare R2 Cleanup ---")


############## API ENDPOINTS ##################################################################################


# Replace the get_session_details function in your main Flask app

@app.route('/api/sessions/<int:session_id>', methods=['GET'])
@login_required
def get_session_details(session_id):
    """
    Loads messages for a specific session after cleaning up any "stopped" events.
    """
    user_id = session['user_id']
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()
    
    # Initial fetch of messages
    messages = ChatMessage.query.filter_by(session_id=chat_session.id).order_by(ChatMessage.timestamp.asc()).all()
    
    # Call the helper to clean the messages; it returns True if changes were made
    deleted_indices = _clean_stopped_messages(messages, s3_client)

    messages_data = []
    for i, m in enumerate(messages):

        if i in deleted_indices:
            continue
    
        if m.message_type == 'user':
            sender = "user"
        else:
            sender = "bot"
        
        if m.is_file_info:
            try:
                file_id = int(m.message_content)
                gen_file = GeneratedFile.query.get(file_id)
                
                if gen_file and not gen_file.is_deleted:
                    file_obj = {"id": gen_file.id, "type": "file", "file_type": gen_file.file_type, "storage_path": gen_file.storage_path, "is_deleted": False, "intro_message": gen_file.intro_message}
                    messages_data.append({"sender": sender, "content": file_obj, "message_type": "file"})
                elif gen_file and gen_file.is_deleted:
                    file_obj = {"id": gen_file.id, "type": "file", "is_deleted": True}
                    messages_data.append({"sender": "bot", "content": file_obj, "message_type": "file"})
                else:
                    messages_data.append({"sender": "bot", "content": f"[Error: File with ID {file_id} not found or was deleted.]", "message_type": "error"})
            except ValueError:
                messages_data.append({"sender": "bot", "content": f"[Error: Malformed file link ({m.message_content})]", "message_type": "error"})
        else:
            messages_data.append({"sender": sender, "content": m.message_content, "message_type": "text"})
    
    return jsonify({"messages": messages_data})


@app.route('/api/sessions', methods=['GET'])
@login_required
def get_all_sessions():
    """
    Gets all chat sessions for the current user.
    """
    user_id = session['user_id']
    sessions = ChatSession.query.filter_by(user_id=user_id).order_by(ChatSession.created_at.desc()).all()
    return jsonify([{
        "id": s.id,
        "title": s.session_title,
        "created_at": s.created_at.isoformat()
    } for s in sessions])

@app.route('/api/sessions', methods=['POST'])
@login_required
def create_new_session():
    """
    Creates a new, blank chat session.
    """
    user_id = session['user_id']
    new_session = ChatSession(user_id=user_id, session_title="New Chat")
    db.session.add(new_session)
    db.session.commit()
    
    return jsonify({"id": new_session.id, "title": new_session.session_title}), 201

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    """
    Deletes a chat session and all its related messages and files
    from both the database and Cloudflare R2 storage.
    """
    user_id = session['user_id']
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()

    if not chat_session:
        return jsonify({"error": "Session not found"}), 404
    
    try:
        # 1. Loop through all files associated with this session
        for file in chat_session.generated_files:
            if file.storage_path:
                try:
                    # 2. Delete each file from Cloudflare R2
                    s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=file.storage_path)
                    print(f"Deleted {file.storage_path} from Cloudflare R2.")
                except Exception as e:
                    # Log if a specific file fails to delete, but don't stop the process
                    print(f"Could not delete file {file.storage_path} from R2: {e}")

        # 3. Delete the session from the database.
        # Cascading deletes will handle removing the ChatMessage and GeneratedFile records.
        db.session.delete(chat_session)
        
        # 4. Commit the changes.
        db.session.commit()

        # 5. Run the full cleanup in a background thread to avoid delaying the response
        def run_cleanup_in_background():
            """Run your existing cleanup file that already works."""
            print("Starting background cleanup after session deletion...")
            
            try:
                cleanup_file = 'cleanup.py'
                
                current_dir = os.path.dirname(os.path.abspath(__file__))
                cleanup_path = os.path.join(current_dir, cleanup_file)
                
                if not os.path.exists(cleanup_path):
                    print(f"Cleanup file not found: {cleanup_path}")
                    return
                
                # Run your existing cleanup file
                result = subprocess.run([
                    sys.executable, 
                    cleanup_path
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print("Background cleanup finished successfully.")
                    if result.stdout:
                        print(result.stdout)
                else:
                    print(f"Background cleanup failed: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print("Background cleanup timed out after 60 seconds.")
            except Exception as e:
                print(f"Error running background cleanup: {e}")

        # Start the cleanup
        cleanup_thread = threading.Thread(target=run_cleanup_in_background)
        cleanup_thread.daemon = True
        cleanup_thread.start()
    
        return jsonify({"message": "Session and all associated files deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting session {session_id}: {e}")
        return jsonify({"error": "An internal error occurred while deleting the session."}), 500


@app.route('/api/sessions/<int:session_id>/message', methods=['POST'])
@login_required
def post_message(session_id):
    """
    Handles a message by acting as a client to the external Chatbot API.
    It now aggregates all generated files into a single response.
    """
    user_id = session['user_id']
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()

    data = request.json
    user_prompt = data.get('message')
    csv_file_id = data.get('data_source_id')
    model_type = data.get('model', 'standard')

    if not user_prompt or not csv_file_id:
        return jsonify({"error": "Message and data_source_id are required"}), 400

    chatbot_api_url = os.environ.get('CHATBOT_API_URL')
    if not chatbot_api_url:
        return jsonify({"error": "Chatbot API service is not configured on the server."}), 500

    data_source = DataSource.query.filter_by(id=csv_file_id, user_id=user_id).first()
    if not data_source:
        return jsonify({"error": "Selected data file not found or you do not have access."}), 404

    user_message_db = ChatMessage(session_id=chat_session.id, message_type='user', message_content=user_prompt)
    db.session.add(user_message_db)
    db.session.commit()

    api_payload = {
        'message': user_prompt,
        'data_source_path': data_source.storage_path,
        'model': model_type,
        'session_id': chat_session.id,
        'user_prompt': user_prompt
    }

    try:
        # We assume the external API can take a while, so a long timeout is appropriate
        api_response = requests.post(chatbot_api_url, json=api_payload, timeout=300)
        api_response.raise_for_status()
        
        response_data = api_response.json()

        # Create a structured response object for the frontend
        bot_response_to_frontend = {
            "text": response_data.get("response", ""),
            "files": []
        }

        # If the API generated files, add them to the files array
        if response_data.get("generated_files"):
            for file_info in response_data["generated_files"]:
                bot_response_to_frontend["files"].append({
                    "type": "file",
                    "file_id": file_info['file_id'],
                    "name": file_info['name'],
                    "intro_message": file_info.get('intro_message', 'Here is the generated file:'),
                    "is_deleted": False,
                    "file_type": file_info.get('file_type', 'unknown')
                })

        # Return the complete, structured response
        return jsonify(bot_response_to_frontend), 200

    except requests.exceptions.RequestException as e:
        print(f"Error calling chatbot API: {e}")
        return jsonify({"error": f"Could not connect to the chatbot service: {e}"}), 503
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An unexpected error occurred while processing the request."}), 500


@app.route('/api/files/<int:file_id>', methods=['DELETE'])
@login_required
def delete_file(file_id):
    """
    Performs a HARD delete from Cloudflare R2 storage,
    but a SOFT delete in the database (sets is_deleted=True).
    """
    user_id = session['user_id']

    db.session.expire_all()  # Clear cache
    
    # Query to ensure the user owns the session this file belongs to
    file_to_delete = GeneratedFile.query.join(ChatSession).filter(
        GeneratedFile.id == file_id,
        ChatSession.user_id == user_id
    ).first()

    if not file_to_delete:
        return jsonify({"error": "File not found or access denied"}), 404

    storage_path = file_to_delete.storage_path
    
    try:
        # 1. Delete the actual file from Cloudflare R2 storage
        print(f"Attempting to delete file from R2: {storage_path}")
        s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=storage_path)
        
        # 2. If R2 deletion is successful, 'soft delete' the record in the database
        file_to_delete.is_deleted = True
        db.session.commit()
        
        print(f"Successfully deleted file {storage_path} from R2 and marked as deleted in DB.")
        return jsonify({"message": "File deleted from storage and marked as deleted"}), 200

    except ClientError as e:
        # If the file deletion from R2 fails, log the error and do not change the database
        print(f"Error deleting file from R2: {e}")
        return jsonify({"error": "Could not delete file from storage."}), 500

@app.route('/api/files/<int:file_id>/download', methods=['GET'])
@login_required
def download_file(file_id):
    """
    Generates a secure, temporary download link for a file in R2.
    """
    user_id = session['user_id']
    
    db.session.expire_all()  # Clear cache
    file_to_download = GeneratedFile.query.join(ChatSession).filter(
        GeneratedFile.id == file_id,
        ChatSession.user_id == user_id,
        GeneratedFile.is_deleted == False
    ).first()
    
    if not file_to_download:
        print(f"File not found: ID={file_id}, User={user_id}")
        return jsonify({"error": "File not found, has been deleted, or access denied"}), 404
    
    try:
        print(f"Generating download URL for file: {file_to_download.storage_path}")
        
        # Generate a pre-signed URL that is valid for 1 hour (3600 seconds)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET_NAME, 'Key': file_to_download.storage_path},
            ExpiresIn=3600
        )
        
        print(f"Generated presigned URL: {presigned_url}")
        
        # Redirect the user to this temporary URL
        return redirect(presigned_url)
    except ClientError as e:
        print(f"Error generating pre-signed URL: {e}")
        return jsonify({"error": "Could not generate download link"}), 500
    

@app.route('/api/initial-data', methods=['GET'])
@login_required
def get_initial_data():
    """
    Provides all necessary data for the initial load and cleans up any
    "stopped" events from the most recent session.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        data_sources = DataSource.query.filter_by(user_id=user_id).order_by(DataSource.created_at.desc()).all()
        sessions_list = ChatSession.query.filter_by(user_id=user_id).order_by(ChatSession.updated_at.desc()).all()

        datasources_data = [{"id": d.id, "filename": d.original_filename} for d in data_sources]
        sessions_data = [{"id": s.id, "title": s.session_title} for s in sessions_list]

        messages_data = []
        active_session_id = None
        if sessions_list:
            active_session_id = sessions_list[0].id
            messages = ChatMessage.query.filter_by(session_id=active_session_id).order_by(ChatMessage.timestamp.asc()).all()
            
            deleted_indices = _clean_stopped_messages(messages, s3_client)

            # Process the final, clean list of messages for the frontend
            for i, m in enumerate(messages):

                if i in deleted_indices:
                    continue

                if m.message_type == 'user':
                    sender = "user"
                else:
                    sender = "bot"
                
                if m.is_file_info:
                    try:
                        file_id = int(m.message_content)
                        gen_file = GeneratedFile.query.get(file_id)
                        
                        if gen_file and not gen_file.is_deleted:
                            file_obj = {"id": gen_file.id, "type": "file", "file_type": gen_file.file_type, "is_deleted": False,
                                        "storage_path": gen_file.storage_path, "intro_message": gen_file.intro_message}
                            messages_data.append({"sender": sender, "content": file_obj, "message_type": "file"})
                        elif gen_file and gen_file.is_deleted:
                            file_obj = {"id": gen_file.id, "type": "file", "is_deleted": True}
                            messages_data.append({"sender": "bot", "content": file_obj, "message_type": "file"})
                        else:
                            messages_data.append({"sender": "bot", "content": f"[Error: File with ID {file_id} not found or was deleted.]", "message_type": "error"})
                    except ValueError:
                        messages_data.append({"sender": "bot", "content": f"[Error: Malformed file link ({m.message_content})]", "message_type": "error"})
                else:
                    messages_data.append({"sender": sender, "content": m.message_content, "message_type": "text"})
        
        response = {
            "data_sources": datasources_data, 
            "sessions": sessions_data, 
            "messages": messages_data, 
            "active_session_id": active_session_id
        }
        return jsonify(response)

    except Exception as e:
        db.session.rollback()
        print(f"Error fetching initial data: {e}")
        return jsonify({"error": "Could not fetch initial data from server."}), 500

@app.route('/api/sessions/<int:session_id>/log-stop', methods=['POST'])
@login_required
def log_generation_stopped(session_id):
    """
    Cleans up the last generated file (if any) and saves a 'stopped' message.
    """
    user_id = session['user_id']
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()

    db.session.expire_all()

    chatbot_api_url = os.environ.get('CHATBOT_API_URL')
    if not chatbot_api_url:
        return jsonify({"error": "Chatbot API service is not configured on the server."}), 500

    stopped_message = ChatMessage(
        session_id=chat_session.id,
        message_type='bot',
        message_content='Response generation stopped.', 
        is_stopped = True
    )
    db.session.add(stopped_message)
    db.session.commit()

    return jsonify({"message": "Stop event logged and cleanup performed"}), 200

@app.route('/api/sessions/<int:session_id>/log-error', methods=['POST'])
@login_required
def log_error(session_id):
    """
    Saves a generic, user-friendly error message to the database
    and prints the technical error to the backend console for debugging.
    """
    # Ensure the user owns the session
    user_id = session.get('user_id')
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()

    # Get the technical error from the frontend for logging
    data = request.json
    technical_error = data.get('error', 'No specific error message provided.')
    print(f"--- CLIENT-SIDE ERROR LOGGED (Session ID: {session_id}) ---\n{technical_error}\n--------------------")

    # Create and save a generic, friendly message to the database
    friendly_error_message = "I'm sorry, an issue occurred. Please try again later."
    
    print("LOG ERROR")
    error_message_db = ChatMessage(
        session_id=chat_session.id,
        message_type='bot',
        message_content=friendly_error_message, 
    )

    db.session.add(error_message_db)
    db.session.commit()
    
    return jsonify({"message": "Error event logged successfully"}), 200

@app.route('/api/sessions/<int:session_id>/title', methods=['POST'])
@login_required
def update_session_title(session_id):
    """
    Checks if the session title has been updated. If not, it updates the title
    based on the user's message, marks it as updated, and returns the new title.
    If it has already been updated, it simply returns the existing title.
    """
    user_id = session['user_id']
    chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first_or_404()

    print("here 1")
    if not chat_session.title_updated:
        # Get the user message from the request body
        data = request.get_json()
        user_message = data.get('userMessage')
        print("here2")

        if user_message and len(user_message.strip()) > 0:
            # Create a new title from the first 25 characters
            print("here3")
            new_title = (user_message[:25] + '...') if len(user_message) > 25 else user_message
            chat_session.session_title = new_title
            chat_session.title_updated = True
            db.session.commit()
    
    return jsonify({"title": chat_session.session_title})

################################### END BOT UI HANDLING ###############################################################

################################### DELETE ACCOUNT ####################################################################

    
# Account Deletion Route
@app.route('/delete_account', methods=['POST'])
def delete_account():
    """
    API endpoint to delete a user account and ALL associated data,
    including uploaded files from Cloudflare R2.
    """
    if not session.get('logged_in'):
        return jsonify({"error": "User not logged in"}), 401
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Invalid session. Please log in again."}), 401

    print(f"--- Initiating account deletion for user_id: {user_id} ---")

    # Use a fresh database session to avoid connection issues
    try:
        # 1. Find the user in the database using the modern SQLAlchemy 2.0 approach
        user_to_delete = db.session.get(User, user_id)

        if not user_to_delete:
            print(f"DELETE FAILED: User with id {user_id} not found.")
            return jsonify({"error": "User account not found"}), 404

        # 2. Get a list of all files uploaded by this user from the data_sources table
        # The `user_to_delete.data_sources` uses the SQLAlchemy relationship we defined.
        files_to_delete_from_r2 = [ds.storage_path for ds in user_to_delete.data_sources]
        
        # We also need to find and delete all AI-generated files from their chat sessions
        for chat_session in user_to_delete.chat_sessions:
            for generated_file in chat_session.generated_files:
                files_to_delete_from_r2.append(generated_file.storage_path)

        # 3. Delete each file from the Cloudflare R2 bucket
        if files_to_delete_from_r2:
            print(f"Found {len(files_to_delete_from_r2)} files to delete from Cloudflare R2.")
            # R2 can delete up to 1000 objects in a single request
            objects_to_delete = [{'Key': file_key} for file_key in files_to_delete_from_r2]
            
            try:
                if s3_client and R2_BUCKET_NAME:
                    s3_client.delete_objects(
                        Bucket=R2_BUCKET_NAME,
                        Delete={'Objects': objects_to_delete}
                    )
                    print("Successfully deleted files from R2.")
                else:
                    print("Warning: R2 client not configured. Skipping file deletion from cloud.")
            except ClientError as e:
                # Log the error but continue, so the user can still be deleted
                print(f"!!! R2 FILE DELETION ERROR: {e}. Proceeding with DB deletion anyway.")

        # 4. Delete the user record from the database.
        # Because we set up `cascade="all, delete-orphan"` in our SQLAlchemy models,
        # deleting the user will automatically delete all of their associated
        # chat_sessions, chat_messages, data_sources, and generated_files records.
        db.session.delete(user_to_delete)
        
        # Commit the transaction
        db.session.commit()
        
        print(f"Successfully deleted user and all associated database records for user_id: {user_id}")

        # 5. Clear the session
        session.clear()
        
        return jsonify({"success": True, "message": "Account and all associated data deleted successfully."})

    except Exception as e:
        # Ensure rollback happens in case of any error
        try:
            db.session.rollback()
        except Exception as rollback_error:
            print(f"!!! Additional error during rollback: {rollback_error}")
        
        print(f"!!! FATAL ERROR during account deletion for user_id {user_id}: {e}")
        return jsonify({"success": False, "error": "An internal error occurred while deleting the account."}), 500
    
    finally:
        # Ensure the session is properly closed to prevent connection leaks
        try:
            db.session.close()
        except Exception as close_error:
            print(f"!!! Error closing database session: {close_error}")

################################### END DELETE ACCOUNT ####################################################################

########### UPLOAD DELETE FILE DASHBOARD ########################################################################################

# Ensure the upload folder exists when running locally
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', './uploads')
ALLOWED_EXTENSIONS = {'csv'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    """Checks if the file's extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_data', methods=['POST'])
def upload_data_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    # A simple check for allowed extensions
    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() == 'csv':
        filename = secure_filename(file.filename)
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        if not s3_client: 
            return jsonify({"success": False, "error": "Cloud storage credentials are not configured on the server."}), 500
        if not R2_BUCKET_NAME:
            return jsonify({"success": False, "error": "Cloud storage bucket name is not configured on the server."}), 500


        # Create a unique filename for storage to avoid conflicts
        unique_filename = f"user_{user_id}/{uuid.uuid4().hex}-{filename}"

        try:
            # Upload the file's content directly to the R2 bucket
            s3_client.upload_fileobj(
                file,           # The file object from Flask
                R2_BUCKET_NAME, # The name of your bucket
                unique_filename # The unique path/name for the file in the bucket
            )

            # Save the metadata to your PostgreSQL database
            new_data_source = DataSource(
                user_id=user_id,
                original_filename=filename,
                storage_path=unique_filename, # Store the unique name, not a local path
                file_type='csv'
            )
            db.session.add(new_data_source)
            db.session.commit()
            
            return jsonify({"success": True, "message": "File uploaded successfully."})

        except ClientError as e:
            print(f"Boto3 Client Error: {e}")
            return jsonify({"success": False, "error": "Could not upload file to cloud storage."}), 500
        except Exception as e:
            db.session.rollback()
            print(f"Database or other error: {e}")
            return jsonify({"success": False, "error": "An internal error occurred."}), 500
    else:
        return jsonify({"success": False, "error": "Invalid file type"}), 400


@app.route('/delete_data_source/<int:data_source_id>', methods=['DELETE'])
def delete_data_source(data_source_id):
    user_id = session.get('user_id')
    if not user_id: return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    if not s3_client: 
        return jsonify({"success": False, "error": "Cloud storage credentials are not configured on the server."}), 500
    if not R2_BUCKET_NAME:
        return jsonify({"success": False, "error": "Cloud storage bucket name is not configured on the server."}), 500


    data_source = DataSource.query.filter_by(id=data_source_id, user_id=user_id).first()
    if not data_source:
        return jsonify({"success": False, "error": "Data source not found"}), 404

    try:
        # Delete the object from the R2 bucket
        s3_client.delete_object(Bucket=R2_BUCKET_NAME, Key=data_source.storage_path)
        
        # Delete the record from the database
        db.session.delete(data_source)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Data source deleted successfully."})

    except ClientError as e:
        print(f"Boto3 Client Error during delete: {e}")
        # Even if file deletion fails, we should probably still allow DB deletion
        db.session.delete(data_source)
        db.session.commit()
        return jsonify({"success": True, "message": "Record deleted, but there was an issue removing the file from storage."})
    except Exception as e:
        db.session.rollback()
        print(f"Database error during delete: {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500


@app.route('/get_data_sources', methods=['GET'])
def get_data_sources():
    if not session.get('logged_in'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    user_id = session['user_id']
    sources = DataSource.query.filter_by(user_id=user_id).order_by(DataSource.created_at.desc()).all()
    
    source_list = [{
        "id": source.id,
        "original_filename": source.original_filename,
        "file_type": source.file_type,
        "created_at": source.created_at.isoformat(),
        "storage_path": source.storage_path
    } for source in sources]
    
    return jsonify({"success": True, "sources": source_list})


########### END UPLOAD DELETE FILE DASHBOARD #################################################################################
        
############## LOG IN ######################################################################################################

@app.route('/')
def serve_index():
    return render_template('login.html')

# Email Confirmation Configuration
confirmation_codes = {}

# Email Configuration (RECOMMENDED: Use Environment Variables for these!)
EMAIL_SENDER_EMAIL = os.environ.get('EMAIL_SENDER_EMAIL')
EMAIL_SENDER_PASSWORD = os.environ.get('EMAIL_SENDER_PASSWORD')
EMAIL_SMTP_SERVER = os.environ.get('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
EMAIL_SMTP_PORT = int(os.environ.get('EMAIL_SMTP_PORT', 587))
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID_HERE")

# --- Helper function to send email confirmation ---
def send_confirmation_email(recipient_email, code, email_type='confirmation'):
    """Sends a 6-digit code (confirmation or reset) to the specified email."""
    if not EMAIL_SENDER_EMAIL or not EMAIL_SENDER_PASSWORD:
        print("Email sender credentials not set. Cannot send email.")
        flash('Email sending is not configured. Please contact support.', 'error')
        return False

    subject = 'Your Account Confirmation Code' if email_type == 'confirmation' else 'Your Password Reset Code'
    content = f"Your {email_type} code is: {code}\n\nThis code will expire in 15 minutes."

    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER_EMAIL
    msg['To'] = recipient_email

    print(f"Attempting to send {email_type} email to {recipient_email} with code {code}...")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            server.starttls(context=context) # For port 587
            server.login(EMAIL_SENDER_EMAIL, EMAIL_SENDER_PASSWORD)
            server.send_message(msg)
        print(f"{email_type.capitalize()} email sent successfully.")
        return True
    except Exception as e:
        print(f"Failed to send {email_type} email to {recipient_email}: {e}")
        flash(f'Failed to send {email_type} email. Please check your email address and try again. Error: {e}', 'error')
        return False

# Login Page Route

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/login')
def serve_login_page():
    return render_template('login.html')

# Perform Login Route
@app.route('/perform_login', methods=['POST'])
def perform_login():
    email = request.form.get('email').strip().lower()
    password = request.form.get('password')

    if not email or not password:
        flash('Email and password are required.', 'error')
        return redirect(url_for('serve_login_page'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            stored_hashed_password = user['password']
            if check_password_hash(stored_hashed_password, password):
                session['logged_in'] = True
                session['user_email'] = user['email']
                session['user_id'] = user['id']
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard_page'))
            else:
                flash('Invalid email or password. Please try again.', 'error')
                return redirect(url_for('serve_login_page'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
            return redirect(url_for('serve_login_page'))
    except Exception as e:
        print(f"Error during login: {e}")
        flash('An error occurred during login. Please try again.', 'error')
        return redirect(url_for('serve_login_page'))
    finally:
        if conn:
            return_db_connection(conn)

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('serve_index'))

# Signup Page Route
@app.route('/signup')
def serve_signup_page():
    return render_template('signup.html')

# Process Signup (Generate Code & Send Email) Route
@app.route('/process_signup', methods=['POST'])
def process_signup():
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if not email or not password or not confirm_password:
        flash('All fields are required!', 'error')
        return redirect(url_for('serve_signup_page'))

    if password != confirm_password:
        flash('Passwords do not match!', 'error')
        return redirect(url_for('serve_signup_page'))

    # Server-side password validation
    if len(password) < 8:
        flash('Password must be at least 8 characters long.', 'error')
        return redirect(url_for('serve_signup_page'))
    if not re.search(r'[a-zA-Z]', password):
        flash('Password must contain at least one letter.', 'error')
        return redirect(url_for('serve_signup_page'))
    if not re.search(r'\d', password):
        flash('Password must contain at least one number.', 'error')
        return redirect(url_for('serve_signup_page'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Email already registered. Please login or use a different email.', 'error')
            return redirect(url_for('serve_signup_page'))

        hashed_password = generate_password_hash(password)
        confirmation_code = ''.join(random.choices('0123456789', k=6))
        
        confirmation_codes[email] = {
            'code': confirmation_code,
            'hashed_password': hashed_password,
            'timestamp': time.time(),
            'type': 'signup'
        }
        
        print(f"Generated signup code for {email}: {confirmation_code}")

        if send_confirmation_email(email, confirmation_code, email_type='confirmation'):
            flash('A confirmation code has been sent to your email. Please enter it below.', 'success')
            return redirect(url_for('serve_verify_email_page', email=email))
        else:
            if email in confirmation_codes:
                del confirmation_codes[email]
            flash('Failed to send confirmation email. Please try again.', 'error')
            return redirect(url_for('serve_signup_page'))
    except Exception as e:
        print(f"Error during signup: {e}")
        flash('An error occurred during signup. Please try again.', 'error')
        return redirect(url_for('serve_signup_page'))
    finally:
        if conn:
            return_db_connection(conn)

# Email Verification Page Route (used for both signup and reset)
@app.route('/verify_email')
def serve_verify_email_page():
    email = request.args.get('email')
    purpose = request.args.get('purpose', 'signup')
    
    if not email:
        flash('No email provided for verification. Please sign up or request password reset again.', 'error')
        if purpose == 'reset':
            return redirect(url_for('serve_reset_password_request_page'))
        return redirect(url_for('serve_signup_page'))
    
    if email not in confirmation_codes:
        flash('No pending verification for this email. Please sign up or request password reset again to receive a new code.', 'error')
        if purpose == 'reset':
            return redirect(url_for('serve_reset_password_request_page'))
        return redirect(url_for('serve_signup_page'))

    return render_template('verify_email.html', email=email, purpose=purpose)

# Confirm Account Route (Final Registration)
@app.route('/confirm_account', methods=['POST'])
def confirm_account():
    email = request.form.get('email')
    entered_code = request.form.get('code')
    purpose = request.form.get('purpose')

    if not email or not entered_code or not purpose:
        flash('Email, code, and purpose are required.', 'error')
        return redirect(url_for('serve_verify_email_page', email=email, purpose=purpose))

    if email not in confirmation_codes or confirmation_codes[email]['type'] != purpose:
        flash('Verification session expired or invalid. Please sign up or request password reset again.', 'error')
        if purpose == 'reset':
            return redirect(url_for('serve_reset_password_request_page'))
        return redirect(url_for('serve_signup_page'))

    stored_data = confirmation_codes[email]
    stored_code = stored_data['code']
    stored_hashed_password = stored_data['hashed_password']
    code_timestamp = stored_data['timestamp']

    if time.time() - code_timestamp > 15 * 60:
        del confirmation_codes[email]
        flash('Confirmation code has expired. Please resend the code.', 'error')
        return redirect(url_for('serve_verify_email_page', email=email, purpose=purpose))

    if entered_code == stored_code:
        if purpose == 'signup':
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, stored_hashed_password))
                conn.commit()
                flash('Account created successfully! You can now log in.', 'success')
                
                if email in confirmation_codes:
                    del confirmation_codes[email]
                
                return redirect(url_for('serve_login_page'))
            except psycopg2.IntegrityError:
                flash('An account with this email already exists. Please login.', 'error')
                return redirect(url_for('serve_login_page'))
            except Exception as e:
                print(f"Error creating account: {e}")
                flash(f'An error occurred during account creation: {e}', 'error')
                return redirect(url_for('serve_signup_page'))
            finally:
                if conn:
                    return_db_connection(conn)
        else: # purpose == 'reset'
            flash('Code verified. Please set your new password.', 'success')
            stored_data['code_verified'] = True
            return redirect(url_for('serve_set_new_password_page', email=email))

    else:
        flash('Invalid confirmation code. Please try again.', 'error')
        return redirect(url_for('serve_verify_email_page', email=email, purpose=purpose))

# Resend Confirmation Code Route
@app.route('/resend_confirmation_code', methods=['POST'])
def resend_confirmation_code():
    email = request.form.get('email')
    purpose = request.form.get('purpose')

    if not email or not purpose:
        flash('Email and purpose are required to resend the code.', 'error')
        if purpose == 'reset':
            return redirect(url_for('serve_reset_password_request_page'))
        return redirect(url_for('serve_signup_page'))

    if email not in confirmation_codes or confirmation_codes[email]['type'] != purpose:
        flash('No pending session found for this email. Please start over.', 'error')
        if purpose == 'reset':
            return redirect(url_for('serve_reset_password_request_page'))
        return redirect(url_for('serve_signup_page'))

    new_confirmation_code = ''.join(random.choices('0123456789', k=6))
    
    confirmation_codes[email]['code'] = new_confirmation_code
    confirmation_codes[email]['timestamp'] = time.time()

    print(f"Resending {purpose} code for {email}: {new_confirmation_code}")

    if send_confirmation_email(email, new_confirmation_code, email_type=purpose):
        flash('A new confirmation code has been sent to your email. Please check and enter it below.', 'success')
    else:
        flash('Failed to resend confirmation email. Please try again or contact support.', 'error')

    return redirect(url_for('serve_verify_email_page', email=email, purpose=purpose))


# Route to serve the password reset request page
@app.route('/reset_password_request')
def serve_reset_password_request_page():
    return render_template('reset_password_request.html')

# Route to handle password reset request (send code)
@app.route('/send_reset_code', methods=['POST'])
def send_reset_code():
    email = request.form.get('email')

    if not email:
        flash('Email address is required to reset password.', 'error')
        return redirect(url_for('serve_reset_password_request_page'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if not existing_user:
            flash('No account found with that email address.', 'error')
            return redirect(url_for('serve_reset_password_request_page'))

        reset_code = ''.join(random.choices('0123456789', k=6))
        
        confirmation_codes[email] = {
            'code': reset_code,
            'hashed_password': None,
            'timestamp': time.time(),
            'type': 'reset',
            'code_verified': False
        }

        print(f"Generated reset code for {email}: {reset_code}")

        if send_confirmation_email(email, reset_code, email_type='reset'):
            flash('A password reset code has been sent to your email. Please enter it below.', 'success')
            return redirect(url_for('serve_verify_email_page', email=email, purpose='reset'))
        else:
            if email in confirmation_codes:
                del confirmation_codes[email]
            flash('Failed to send reset email. Please try again.', 'error')
            return redirect(url_for('serve_reset_password_request_page'))
    except Exception as e:
        print(f"Error sending reset code: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('serve_reset_password_request_page'))
    finally:
        if conn:
            return_db_connection(conn)

# Route to serve the set new password page (after code verification)
@app.route('/set_new_password')
def serve_set_new_password_page():
    email = request.args.get('email')
    
    if not email or email not in confirmation_codes or confirmation_codes[email].get('code_verified') != True:
        flash('Invalid session for password reset. Please request a new reset.', 'error')
        return redirect(url_for('serve_reset_password_request_page'))

    return render_template('set_new_password.html', email=email)

# Route to handle setting the new password
@app.route('/perform_password_reset', methods=['POST'])
def perform_password_reset():
    email = request.form.get('email')
    new_password = request.form.get('new_password')
    confirm_new_password = request.form.get('confirm_new_password')

    if not email or not new_password or not confirm_new_password:
        flash('All fields are required.', 'error')
        return redirect(url_for('serve_set_new_password_page', email=email))
    
    if new_password != confirm_new_password:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('serve_set_new_password_page', email=email))

    # Server-side password validation for new password during reset
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'error')
        return redirect(url_for('serve_set_new_password_page', email=email))
    if not re.search(r'[a-zA-Z]', new_password):
        flash('New password must contain at least one letter.', 'error')
        return redirect(url_for('serve_set_new_password_page', email=email))
    if not re.search(r'\d', new_password):
        flash('New password must contain at least one number.', 'error')
        return redirect(url_for('serve_set_new_password_page', email=email))

    if email not in confirmation_codes or confirmation_codes[email].get('code_verified') != True:
        flash('Invalid or expired reset session. Please request a new password reset.', 'error')
        return redirect(url_for('serve_reset_password_request_page'))
    
    hashed_new_password = generate_password_hash(new_password)

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_new_password, email))
                conn.commit()
                if cursor.rowcount == 0:
                    flash('Error updating password. User not found.', 'error')
                    return redirect(url_for('serve_reset_password_request_page'))
    finally:
        return_db_connection(conn)

    if email in confirmation_codes:
        del confirmation_codes[email]

    flash('Your password has been successfully reset. You can now log in with your new password.', 'success')
    return redirect(url_for('serve_login_page'))


# Dashboard/Success Page Route
@app.route('/dashboard')
def dashboard_page():
    user_email = session.get('user_email')
    # print(f"DEBUG: user_email = {user_email}")  
    # print(f"DEBUG: session = {dict(session)}")
    if not session.get('logged_in'):
        flash('Please log in to access the dashboard.', 'info')
        return redirect(url_for('serve_login_page')) # Redirect to login page if not logged in
    return render_template('dashboard.html', user_email = user_email)

@app.route("/auth/google/callback", methods=["POST"])
def google_callback():
    try:
        # Add some debugging
        print(f"Request method: {request.method}")
        print(f"Request headers: {dict(request.headers)}")
        print(f"Request data: {request.get_data()}")
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No JSON data received"}), 400
            
        token = data.get('token')
        if not token:
            return jsonify({"success": False, "message": "No token provided"}), 400
            
        idinfo = id_token.verify_oauth2_token(token, google_auth_requests.Request(), GOOGLE_CLIENT_ID)
        google_user_id = idinfo['sub']
        user_email = idinfo.get('email', '').strip().lower()
        
        user = User.query.filter_by(google_id=google_user_id).first()
        if not user:
            user = User.query.filter(sqlalchemy_func.lower(User.email) == user_email).first()
            if user:
                user.google_id = google_user_id
            else:
                user = User(email=user_email, password=generate_password_hash(os.urandom(24).hex()), google_id=google_user_id)
                db.session.add(user)
            db.session.commit()
        
        session.clear()
        session['logged_in'] = True
        session['user_email'] = user.email
        session['user_id'] = user.id
        print(f"Created session for user: {user.email}")
        
        return jsonify({"success": True})
        
    except Exception as e:
        db.session.rollback()
        print(f"!!! GOOGLE AUTH ERROR: {e}")
        import traceback
        traceback.print_exc()  # This will help debug the exact error
        return jsonify({"success": False, "message": "An error occurred during Google authentication."}), 500

########### END LOG IN ######################################################################################################


if __name__ == '__main__':
    # Set these environment variables before running the app
    # Example for development (replace with your actual values):
    # export FLASK_SECRET_KEY='your_very_strong_and_unique_secret_key_here_for_security'
    # export EMAIL_SENDER_EMAIL='your.sending.email@example.com'
    # export EMAIL_SENDER_PASSWORD='your_email_app_password_or_regular_password' # Use app password for Gmail with 2FA
    # export EMAIL_SMTP_SERVER='smtp.gmail.com'
    # export EMAIL_SMTP_PORT='587'
    # export GOOGLE_CLIENT_ID="your-client-id-here"
    # export DATABASE_URL='postgresql://username:password@host:port/database_name'
    # export CHATBOT_API_URL="bot_api_link/api/chatbot/ask"
    # export R2_ACCOUNT_ID="..."
    # export R2_ACCESS_KEY_ID="..."
    # export R2_SECRET_ACCESS_KEY="..."
    # export R2_BUCKET_NAME="..."
    # export R2_PUBLIC_URL="..."

    app.run(host='0.0.0.0', port=5001, debug=True)