#!/opt/hiddify-manager/.venv313/bin/python

from asgiref.wsgi import WsgiToAsgi

from hiddifypanel import create_app_wsgi

app = create_app_wsgi()  # noqa
asgi_app = WsgiToAsgi(app)
