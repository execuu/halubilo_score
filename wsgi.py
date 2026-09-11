"""Native WSGI entry point shared by Gunicorn and PythonAnywhere."""
from app import create_app
app = create_app()
application = app
