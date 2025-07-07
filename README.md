# AI Data Analyst Chatbot

This web application is an interactive platform where users can upload CSV data and use a powerful AI assistant to perform data analysis, generate insights, and create visualizations. Users can ask questions in plain English, and the backend will generate and execute Python code to produce answers, charts, and new data files.

## Key Features

* **Secure User Authentication:** A complete system including standard Login/Signup, Google Sign-In, and password reset functionality via email OTP.
* **Data Source Management:** Users can upload, view, and delete their personal CSV files through a user-friendly dashboard.
* **Interactive Chat & Analysis:** A responsive, multi-session chat interface for data analysis using natural language prompts.
* **AI-Powered File Generation:** Dynamically creates and displays plots (`.png`) and data files (`.csv`) based on user requests.
* **Full Lifecycle Control:** Users have complete control, with the ability to:
    * Stop long-running AI responses directly from the UI.
    * Download or delete individual generated files.
    * Delete entire chat sessions.
    * Securely delete their entire account and all associated data.
* **Secure & Scalable Storage:** Uses Cloudflare R2 for robust object storage of all user-uploaded data and AI-generated files.
* **Automated Maintenance:** A background cron job periodically cleans up any orphaned files and database records to maintain system integrity.
* **Modern UX:** A responsive interface with loading indicators and toast notifications for a smooth user experience.

## Technology Stack

* **Backend:** Flask, Flask-SQLAlchemy, Gunicorn
* **Database:** PostgreSQL
* **AI:** Google Generative AI (Gemini)
* **Object Storage:** Cloudflare R2 (via Boto3)
* **Data Handling:** Pandas, Matplotlib
* **Frontend:** Vanilla JavaScript (ES6+), HTML5, CSS3
* **Authentication:** Google Identity Services, Werkzeug (for password hashing)

## Setup and Installation

Follow these steps to get the application running locally.

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/Jonathan-Tjandra/AIDataAnalyst.git
    cd AIDataAnalyst
    ```

2.  **Create and Activate a Virtual Environment**
    ```bash
    # On macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # On Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install Dependencies**
    Install all the required packages from the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables**
    Create a file named `.env` in the root directory of the project. This file stores your secret keys and configuration. Add the following variables:

    ```
    # Flask & Database Configuration
    FLASK_SECRET_KEY='a_very_long_and_random_secret_key_here'
    DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DATABASE_NAME'

    # External Chatbot API URL
    CHATBOT_API_URL='http://127.0.0.1:5002/api/chatbot/ask'

    # Google API & OAuth
    GOOGLE_API_KEY='your_google_ai_api_key'
    GOOGLE_CLIENT_ID='your_google_oauth_client_id.apps.googleusercontent.com'

    # Cloudflare R2 Credentials
    R2_ACCOUNT_ID='your_r2_account_id'
    R2_ACCESS_KEY_ID='your_r2_access_key_id'
    R2_SECRET_ACCESS_KEY='your_r2_secret_access_key'
    R2_BUCKET_NAME='your_r2_bucket_name'
    
    # Email Configuration (for password reset)
    EMAIL_SENDER_ADDRESS='your_sender_email@example.com'
    EMAIL_SENDER_PASSWORD='your_email_app_password'
    EMAIL_SMTP_SERVER='smtp.gmail.com'
    EMAIL_SMTP_PORT='587'
    ```

5.  **Configure Google Cloud Credentials**
    For Google Sign-In to work, you must add your application's URLs to your Google Cloud Console credentials.

    -   Go to the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
    -   Select your OAuth 2.0 Client ID.
    -   Under **Authorised JavaScript origins**, add the URLs where your app will run. For local testing, add:
        -   `http://127.0.0.1:5001`
        -   Your ngrok URL (e.g., `https://your-id.ngrok-free.app`)
    -   Under **Authorised redirect URIs**, add the URLs with the callback path. For local testing, add:
        -   `http://127.0.0.1:5001/auth/google/callback`
        -   Your ngrok URL with the callback path (e.g., `https://your-id.ngrok-free.app/auth/google/callback`)

6.  **Initialize the Database**
    The first time you run the application, the database tables will be created automatically based on the models defined in your code.

## Running the Application

1.  **Run the Web Server**
    Start the Flask development server from your terminal. By default, it runs on port 5001.
    ```bash
    flask run
    ```
    The application will be available at `http://127.0.0.1:5001`.

2.  **Using ngrok for External Access (Optional)**
    If you need to access your local server from the internet (e.g., for testing Google Sign-In callbacks), you can use ngrok.

    -   First, make sure your Flask app is running.
    -   Open a **new, separate terminal window**.
    -   Run the following command. Make sure the port number matches the port your Flask application is running on.
        ```bash
        ngrok http 5001
        ```
    -   ngrok will provide you with a public URL (e.g., `https://<random-id>.ngrok-free.app`). You can use this URL in your browser to access your local application.

3.  **Running and Scheduling the Cleanup Script (Optional)**

    This script deletes orphaned files from Cloudflare R2 and the database.

    **To run it manually:**
    ```bash
    python cleanup.py
    ```

    **To schedule it to run automatically:**

    * **On a Hosting Platform (like Render):** Use the platform's built-in "Cron Job" feature. Set the schedule (e.g., `0 3 * * *` for 3:00 AM UTC daily) and the command (`python cleanup.py`).

    * **On macOS or Linux:** Use `cron`. Open your terminal and run `crontab -e`. Add the following line to run the script daily at 3:00 AM, making sure to use the **full paths** to your Python executable and script:
        ```
        0 3 * * * /path/to/your/venv/bin/python /path/to/your/project/cleanup.py
        ```

    * **On Windows:** Use **Task Scheduler**. Create a new task, set a daily trigger (e.g., 3:00 AM), and for the "Action," set "Program/script" to the full path of your `python.exe` and "Add arguments" to `cleanup.py`.