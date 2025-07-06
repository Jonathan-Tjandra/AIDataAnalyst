import os
import google.generativeai as genai
from flask import request, jsonify
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use a non-interactive backend for Matplotlib
import matplotlib.pyplot as plt
import io
import uuid
import boto3
import json
import time
from typing import Optional
import uuid
from ui import db, GeneratedFile, app, ChatMessage


# --- CONFIGURATION ---
class GoogleAPIKeyManager:
    def __init__(self, api_keys_string: str):
        """Initialize with comma-separated API keys string"""
        self.api_keys = [key.strip() for key in api_keys_string.split(',') if key.strip()]
        self.current_key_index = 0
        self.failed_keys = set()  # Track temporarily failed keys
        self.last_reset_time = time.time()
        self.reset_interval = 12600  # Reset failed keys every 6 hours
        
        if not self.api_keys:
            raise ValueError("No valid API keys provided")
        
        print(f"Initialized with {len(self.api_keys)} Google API keys")
    
    def get_current_key(self) -> str:
        """Get the current API key"""
        self._reset_failed_keys_if_needed()
        return self.api_keys[self.current_key_index]
    
    def rotate_key(self) -> bool:
        """Rotate to the next available API key. Returns True if rotation successful."""
        self._reset_failed_keys_if_needed()
        
        # Mark current key as failed
        current_key = self.api_keys[self.current_key_index]
        self.failed_keys.add(current_key)
        print(f"Marking API key ending in ...{current_key[-4:]} as temporarily failed")
        
        # Find next available key
        start_index = self.current_key_index
        for _ in range(len(self.api_keys)):
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            current_key = self.api_keys[self.current_key_index]
            
            if current_key not in self.failed_keys:
                print(f"Rotated to API key ending in ...{current_key[-4:]}")
                return True
        
        # If all keys are failed, reset and try again
        print("All API keys are temporarily failed, resetting...")
        self.failed_keys.clear()
        self.current_key_index = (start_index + 1) % len(self.api_keys)
        return True
    
    def _reset_failed_keys_if_needed(self):
        """Reset failed keys if enough time has passed"""
        current_time = time.time()
        if current_time - self.last_reset_time > self.reset_interval:
            if self.failed_keys:
                print(f"Resetting {len(self.failed_keys)} failed API keys after {self.reset_interval} seconds")
                self.failed_keys.clear()
            self.last_reset_time = current_time
    
    def get_available_keys_count(self) -> int:
        """Get count of currently available (non-failed) keys"""
        self._reset_failed_keys_if_needed()
        return len(self.api_keys) - len(self.failed_keys)

# Initialize API Key Manager
try:
    GOOGLE_API_KEYS_STRING = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEYS_STRING:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    api_key_manager = GoogleAPIKeyManager(GOOGLE_API_KEYS_STRING)
    genai.configure(api_key=api_key_manager.get_current_key())
except Exception as e:
    print(f"Error configuring Google AI: {e}")
    exit()

R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')

s3_client = None
if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
    s3_client = boto3.client(
        's3',
        endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )


with app.app_context():
    # Check if table exists
    db.create_all()
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()

def generate_file_intro_message(user_message, file_type, file_content_summary=None, model_type='standard'):
    """
    Generate an introductory message for a generated file using Gemini API
    """
    try:
        # Get API key from your api_key_manager
        api_key = api_key_manager.get_current_key()
        if not api_key:
            return "I've generated a file based on your request."
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Choose model based on model_type
        if model_type == 'premium':
            model = genai.GenerativeModel('gemini-1.5-pro')
        else:
            model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create context-aware prompt
        if file_type == 'png':
            file_description = "visualization/chart/graph"
        elif file_type == 'csv':
            file_description = "data analysis results in CSV format"
        else:
            file_description = "file"
        
        prompt = f"""
        Generate a brief, friendly introductory message (1-2 sentences) for a {file_description} that was created based on this user request: "{user_message}"
        
        The message should:
        - Be conversational and helpful
        - Explain what the file contains or shows
        - Not mention technical details about file formats
        - Be under 100 words
        - Start naturally (avoid "Here is..." or "I have created...")
        
        Example styles:
        - "This visualization shows the sales trends across different regions for the past quarter."
        - "The analysis reveals interesting patterns in customer behavior throughout the year."
        - "Based on your data, I've identified the top performing products and their monthly sales figures."
        """
        
        if file_content_summary:
            prompt += f"\n\nAdditional context about the file content: {file_content_summary}"
        
        response = model.generate_content(prompt)
        intro_message = response.text.strip()
        
        # Fallback if response is too long or empty
        if not intro_message or len(intro_message) > 200:
            if file_type == 'png':
                return f"I've created a visualization based on your request about {user_message[:50]}{'...' if len(user_message) > 50 else ''}."
            elif file_type == 'csv':
                return f"Here's the data analysis you requested, exported as a downloadable file."
            else:
                return "I've generated a file based on your request."
        
        return intro_message
        
    except Exception as e:
        print(f"Error generating intro message: {e}")
        # Fallback messages
        if file_type == 'png':
            return "I've created a visualization based on your data analysis request."
        elif file_type == 'csv':
            return "Here are the results of your data analysis, ready for download."
        else:
            return "I've generated a file based on your request."


def call_gemini_with_retry(prompt: str, model_type: str = 'standard', max_retries: int = 3) -> tuple[Optional[str], Optional[str]]:
    """Call Gemini API with automatic key rotation and model selection."""
    
    # Map frontend model selection to the official Google model names
    model_map = {
        'standard': 'gemini-1.5-flash',
        'premium': 'gemini-1.5-pro'
    }
    # Default to the standard model if the selection is invalid
    model_name = model_map.get(model_type, 'gemini-1.5-flash')
    
    print(f"Attempting to use model: {model_name}")

    for attempt in range(max_retries):
        try:
            # Configure with current API key
            current_key = api_key_manager.get_current_key()
            genai.configure(api_key=current_key)
            
            # Use the dynamically selected model name
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            print(f"Successfully used API key ending in ...{current_key[-4:]} with model {model_name} (attempt {attempt + 1})")
            return response.text, None
            
        except Exception as e:
            error_str = str(e).lower()
            print(f"Attempt {attempt + 1} failed with error: {e}")
            
            # Check if it's a rate limit or quota error
            if any(keyword in error_str for keyword in [
                'quota', 'rate limit', 'too many requests', 'resource_exhausted', 
                'rate_limit_exceeded', '429', 'quota exceeded'
            ]):
                if api_key_manager.get_available_keys_count() > 1:
                    print("Rate limit detected, rotating API key...")
                    api_key_manager.rotate_key()
                    time.sleep(1)  # Brief pause before retry
                    continue
                else:
                    print("All API keys are rate limited")
            
            # For other errors, still try rotating if we have more attempts
            if attempt < max_retries - 1 and api_key_manager.get_available_keys_count() > 1:
                print("Non-rate-limit error, trying different API key...")
                api_key_manager.rotate_key()
                time.sleep(1)
                continue
            
            # If this is the last attempt or no more keys available
            return None, f"Failed after {max_retries} attempts. Last error: {e}"
    
    return None, f"All attempts failed"


def generate_python_code(question, csv_headers, model = 'standard'):
    prompt = f"""
        You are an expert Python data analyst. Your task is to write a Python script to answer a user's question about a given CSV file.

        You must only use the pandas and matplotlib libraries.
        The script will be executed in an environment where:
        - pandas is imported as `pd`
        - matplotlib.pyplot is imported as `plt`
        - The CSV data is pre-loaded into a pandas DataFrame called `df`.

        Your script MUST do one of the following:
        1.  If the user asks for a graph or plot, generate a plot using matplotlib. Do not call `plt.show()`.
        2.  If the user asks for a table or data analysis (like a crosstab), create a new pandas DataFrame with the result and assign it to a variable named `result_df`.
        3.  If the question is a simple lookup that can be answered with text (e.g., "What is the average temperature?"), use the `print()` function to output the answer as a string.

        **IMPORTANT RULES:**
        - Your output MUST be a single, executable Python code block.
        - Do NOT include the `df = pd.read_csv(...)` line. The DataFrame `df` is already loaded.
        - Do NOT include any explanations, comments, or markdown formatting like ```python.
        - For plots, make them visually appealing: add titles, labels, and use `plt.tight_layout()`.

        ### CSV File Headers:
        {csv_headers}

        ### User Question:
        "{question}"

        ### Python Code:
        """
    
    response_text, error = call_gemini_with_retry(prompt, model)
    if error:
        print(f"Error calling Gemini API for code generation: {error}")
        return None, error
    
    python_code = response_text.strip().replace('```python', '').replace('```', '').strip()
    print(f"--- AI Generated Python Code ---\n{python_code}\n--------------------------------")
    return python_code, None


def interpret_data_for_user(question, data,  model = 'standard'):
    """This is our English 'Summarizer' AI."""
    
    if isinstance(data, dict) and 'error' in data:
        prompt = f"""You are a helpful assistant. The user asked: "{question}". The database query failed with the following error: "{data['error']}". Apologize and kindly ask the user to rephrase the question. The response must be in English."""
    elif not data:
        prompt = f"""The user asked: "{question}". The SQL query returned no results. Inform the user in English that no relevant information was found."""
    else:
        prompt = f"""You are a helpful assistant. The user asked: "{question}". Based ONLY on the following data, write a clear and friendly answer in English. If presenting a list, use bullet points. Data: {json.dumps(data, indent=2)}"""

    response_text, error = call_gemini_with_retry(prompt, model)
    if error:
        print(f"Error calling Gemini API for interpretation: {error}")
        return "Sorry, I encountered an issue while formulating the answer."
    
    return response_text


def with_main_app_context(func):
    def wrapper(*args, **kwargs):
        with app.app_context():
            return func(*args, **kwargs)
    return wrapper

@app.route('/api/chatbot/ask', methods=['POST'])
@with_main_app_context
def chat_endpoint():

    # --- Helper function to process and upload a single plot ---
    def _process_plot(fig_num, session_id, user_prompt, model_type):
        try:
            plt.figure(fig_num) # Switch to the correct figure
            
            # Create DB records
            new_file = GeneratedFile(chat_session_id=session_id, original_prompt=user_prompt, file_type='png', storage_path='', intro_message='')
            db.session.add(new_file)
            db.session.flush() # Get the ID

            file_message = ChatMessage(session_id=session_id, message_type='bot', message_content=f"{new_file.id}", is_file_info=True)
            db.session.add(file_message)

            # Upload to Cloudflare
            unique_filename = f"generated/{new_file.id}_{uuid.uuid4().hex}.png"
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            s3_client.upload_fileobj(buf, R2_BUCKET_NAME, unique_filename, ExtraArgs={'ContentType': 'image/png'})
            
            # Generate intro and update record
            chart_intro = generate_file_intro_message(user_message, 'png', None, model_type)
            new_file.storage_path = unique_filename
            new_file.intro_message = chart_intro
            
            return {"file_id": new_file.id, "name": unique_filename.split('/')[-1], "intro_message": chart_intro, "file_type": "png"}
        except Exception as e:
            print(f"Error processing plot {fig_num}: {e}")
            db.session.rollback() # Rollback this specific file's transaction
            return None # Indicate failure

    # --- Helper function to process and upload a single CSV ---
    def _process_csv(df_variable_name, dataframe, session_id, user_prompt, model_type):
        try:
            # Create DB records
            new_file = GeneratedFile(chat_session_id=session_id, original_prompt=user_prompt, file_type='csv', storage_path='', intro_message='')
            db.session.add(new_file)
            db.session.flush() # Get the ID

            file_message = ChatMessage(session_id=session_id, message_type='bot', message_content=f"{new_file.id}", is_file_info=True)
            db.session.add(file_message)

            # Upload to Cloudflare
            unique_filename = f"generated/{new_file.id}_{uuid.uuid4().hex}.csv"
            csv_buffer = io.StringIO()
            dataframe.to_csv(csv_buffer, index=False)
            s3_client.put_object(Bucket=R2_BUCKET_NAME, Key=unique_filename, Body=csv_buffer.getvalue(), ContentType='text/csv')
            
            # Generate intro and update record
            csv_summary = f"File '{df_variable_name}.csv' contains {len(dataframe)} rows with columns: {', '.join(dataframe.columns)}"
            csv_intro = generate_file_intro_message(user_message, 'csv', csv_summary, model_type)
            new_file.storage_path = unique_filename
            new_file.intro_message = csv_intro
            
            return {"file_id": new_file.id, "name": unique_filename.split('/')[-1], "intro_message": csv_intro, "file_type": "csv"}
        except Exception as e:
            print(f"Error processing dataframe '{df_variable_name}': {e}")
            db.session.rollback() # Rollback this specific file's transaction
            return None # Indicate failure

    # --- Main function logic starts here ---
    data = request.get_json()
    user_message = data.get('message', '')
    data_source_path = data.get('data_source_path')
    model_type = data.get('model', 'standard')
    session_id = data.get('session_id')
    user_prompt = data.get('user_prompt')

    if not all([user_message, data_source_path, s3_client, R2_BUCKET_NAME, session_id]):
        return jsonify({"error": "Message, data_source_path, session_id, and storage configuration are required"}), 400

    print(f"Received message: '{user_message}' for data source: '{data_source_path}' using model: '{model_type}'")
    
    try:
        csv_obj = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=data_source_path)
        df = pd.read_csv(io.BytesIO(csv_obj['Body'].read()))
        csv_headers = ", ".join(df.columns)
    except Exception as e:
        return jsonify({"response": f"Error reading data source: {e}"}), 500

    generated_code, error = generate_python_code(user_message, csv_headers, model_type)
    if error:
        return jsonify({"response": f"I had trouble understanding that. {error}"}), 500

    captured_output = io.StringIO()
    response_data = {"response": "", "generated_files": []}

    try:
        local_scope = {
            'pd': pd,
            'plt': plt,
            'df': df,
            'print': lambda *args, **kwargs: print(*args, file=captured_output, **kwargs),
            'question': user_message
        }
        
        exec(generated_code, {}, local_scope)

        with app.app_context():
            # Sequentially check for and process any generated plots
            if 'plt' in local_scope and plt.get_fignums():
                for fig_num in plt.get_fignums():
                    plot_data = _process_plot(fig_num, session_id, user_prompt, model_type)
                    if plot_data:
                        response_data["generated_files"].append(plot_data)
                plt.close('all')

            # Sequentially check for and process any generated DataFrames
            for var_name, var_value in local_scope.items():
                # Process any new pandas DataFrame created, ignoring the original 'df'
                if isinstance(var_value, pd.DataFrame) and var_name != 'df':
                    csv_data = _process_csv(var_name, var_value, session_id, user_prompt, model_type)
                    if csv_data:
                        response_data["generated_files"].append(csv_data)

            # Process any text output printed during execution
            printed_output = captured_output.getvalue().strip()
            text_explanation = ""

            if printed_output:
                text_explanation = printed_output
                bot_message = ChatMessage(session_id=session_id, message_type='bot', message_content=text_explanation)
                db.session.add(bot_message)
            # If no text was printed but files were made, the response can be empty
            elif response_data["generated_files"]:
                pass 
            # If nothing was generated at all, provide a default message
            else:
                text_explanation = "I have processed your request. If you expected a file or a specific answer, please try rephrasing."
                bot_message = ChatMessage(session_id=session_id, message_type='bot', message_content=text_explanation)
                db.session.add(bot_message)

            response_data["response"] = text_explanation
            
            # Commit all successful DB changes at the very end
            db.session.commit()
            
            return jsonify(response_data)

    except Exception as e:
        print(f"!!! EXECUTION ERROR: {e}")
        plt.close('all')
        db.session.rollback()
        return jsonify({"response": f"I'm sorry, I encountered an error while analyzing the data: {e}"}), 500

if __name__ == '__main__':
    # export GOOGLE_API_KEY="key1,key2,..."
    # export R2_ACCOUNT_ID="..."
    # export R2_ACCESS_KEY_ID="..."
    # export R2_SECRET_ACCESS_KEY="..."
    # export R2_BUCKET_NAME="..."
    app.run(host='0.0.0.0', port=5002, debug=True)