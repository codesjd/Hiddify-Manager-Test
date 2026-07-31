#!/opt/hiddify-manager/.venv313/bin/python

if __name__ == "__main__":
    import bjoern
    import hiddifypanel
    app = hiddifypanel.create_app()
    from hiddifypanel.apps.scheduler import start as start_scheduler
    start_scheduler(app)
    bjoern.run(wsgi_app=app, host="127.0.0.1", port=9000)
