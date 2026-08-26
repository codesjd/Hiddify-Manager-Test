import pytest
from hiddifypanel.models.routing import get_available_inbound_tags
from hiddifypanel.models import Child, Domain, Proxy, DomainType
from hiddifypanel.models.config import set_hconfig
from hiddifypanel.models.config_enum import ConfigEnum
from hiddifypanel.database import db
import time

def test_benchmark_inbounds(app):
    with app.app_context():
        # Clean db first just in case
        db.session.query(Domain).delete()
        db.session.query(Child).delete()
        db.session.commit()

        # Create child
        child = Child(unique_id="bench_child")
        db.session.add(child)
        db.session.commit()
        child_id = child.id

        set_hconfig(ConfigEnum.core_type, 'xray', child.id)
        set_hconfig(ConfigEnum.reality_enable, True, child.id)
        set_hconfig(ConfigEnum.tuic_enable, True, child.id)
        set_hconfig(ConfigEnum.hysteria_enable, True, child.id)
        set_hconfig(ConfigEnum.naive_enable, True, child.id)

        for i in range(100):
            d1 = Domain(domain=f"reality{i}.com", mode=DomainType.special_reality_tcp, internal_port_special=10000+i, child_id=child.id)
            d2 = Domain(domain=f"tuic{i}.com", mode=DomainType.tuic, internal_port_tuic=20000+i, child_id=child.id)
            d3 = Domain(domain=f"hysteria{i}.com", mode=DomainType.hysteria, internal_port_hysteria2=30000+i, child_id=child.id)
            db.session.add_all([d1, d2, d3])
        db.session.commit()

        # monkeypatch Child.current to return our child
        from hiddifypanel.models.child import Child
        original_current = Child.current
        Child.current = lambda: child

        start = time.perf_counter()
        iters = 50
        for _ in range(iters):
            get_available_inbound_tags()
        duration = time.perf_counter() - start
        print(f"\nBaseline for {iters} iterations: {duration:.4f} seconds")
        print(f"Time per iteration: {(duration/iters)*1000:.4f} ms")

        # restore
        Child.current = original_current
