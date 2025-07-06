# Run periodically to clean up orphaned files or DB record in unexpected edge cases not handled (if any).

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()
from ui import app, cleanup_db_orphans, cleanup_r2_orphans


def main():
    """Main function to run the cleanup tasks within the app context."""
    print("Starting periodic cleanup process...")
    with app.app_context():
        cleanup_db_orphans()
        cleanup_r2_orphans()
    print("Cleanup process finished.")


if __name__ == "__main__":
    # export R2_ACCOUNT_ID="..."
    # export R2_ACCESS_KEY_ID="..."
    # export R2_SECRET_ACCESS_KEY="..."
    # export R2_BUCKET_NAME="..."
    main()