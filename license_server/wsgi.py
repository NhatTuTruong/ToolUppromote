"""WSGI entry cho Gunicorn / uWSGI: gunicorn -w 2 -b 0.0.0.0:8765 license_server.wsgi:application"""
from license_server.app import app as application
