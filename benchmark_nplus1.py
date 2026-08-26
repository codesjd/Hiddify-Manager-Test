import sys
import os

# Append the src directory to path
sys.path.append(os.path.join(os.getcwd(), 'hiddify-panel', 'src'))

from hiddifypanel import create_app
from hiddifypanel.models import Domain, Proxy, StrConfig, BoolConfig
import time

app = create_app()

with app.app_context():
    # Insert some fake data
    from hiddifypanel.database import db
    from hiddifypanel.models import DomainType

    # Check if there's any domains, else add some
    for i in range(100):
        d = Domain(domain=f"test{i}.com", mode=DomainType.direct)
        db.session.add(d)

        p = Proxy(name=f"test{i}", enable=True)
        db.session.add(p)

    db.session.commit()

    from hiddifypanel.hutils.node.child import __get_sync_data_for_api, SyncFields

    start = time.time()
    for _ in range(10):
        __get_sync_data_for_api()
    end = time.time()
    print(f"Time taken for baseline: {end - start:.4f}s")
