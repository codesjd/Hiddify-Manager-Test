import pytest
from hiddifypanel.models import Domain, Proxy, ConfigEnum, DomainType, User
from hiddifypanel.hutils.proxy.shared import make_proxy

@pytest.fixture
def seeded_app(app):
    with app.app_context():
        from hiddifypanel.database import db
        from hiddifypanel.panel.init_db import init_db
        init_db()
        
        Domain.query.delete()
        User.query.delete()
        Proxy.query.delete()
        
        d = Domain(domain="test.hiddify.com", mode=DomainType.direct, alias="Test Direct")
        db.session.add(d)
        
        u = User(uuid="11111111-1111-1111-1111-111111111111", name="test_user", enable=True)
        db.session.add(u)
        
        # AnyTLS VLESS Proxy
        p1 = Proxy(name="VLESS AnyTLS", proto="VLESS", transport="WS", l3="tls", cdn="other", enable=True)
        db.session.add(p1)
        
        db.session.commit()
    yield app

def test_render_golden_proxies(seeded_app):
    with seeded_app.app_context():
        from hiddifypanel.database import db
        user = User.query.first()
        domain = Domain.query.first()
        
        proxies = db.session.query(Proxy).filter(Proxy.enable == True).all()
        results = []
        for p in proxies:
            res = make_proxy(p, domain, user, "singbox")
            if res:
                results.append(res)
        
        assert len(results) == 1
        first = results[0]
        assert first["server"] == "test.hiddify.com"
        assert first["port"] == 443
        assert first["type"] == "vless"
        assert first["transport"] == "WS"

