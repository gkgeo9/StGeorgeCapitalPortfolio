# wsgi.py
"""
WSGI entry point for production deployment.
This is what gunicorn will import.
"""

from app import create_app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    app.run()
