from apscheduler.schedulers.background import BackgroundScheduler
_scheduler = None

def start(app):
    global _scheduler
    if _scheduler is not None:
        return
    def _usage():
        with app.app_context():
            from hiddifypanel.panel import usage
            usage.update_local_usage()
    def _backup():
        with app.app_context():
            from hiddifypanel.panel.cli import backup_task
            backup_task()
    sch = BackgroundScheduler(timezone="UTC")
    sch.add_job(_usage, "interval", seconds=60, max_instances=1, coalesce=True, id="update_usage")
    sch.add_job(_backup, "cron", hour="*/6", minute=0, max_instances=1, id="backup_task")
    sch.start()
    _scheduler = sch
