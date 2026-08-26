import time
from marshmallow import Schema, fields

# Mock schemas similar to the real ones
class DomainSchema(Schema):
    domain = fields.String(required=True)
    mode = fields.String(required=True)
    alias = fields.String(allow_none=True)
    sub_link_only = fields.Boolean(required=True)

class ProxySchema(Schema):
    name = fields.String()
    enable = fields.Boolean()
    proto = fields.String()

class HConfigSchema(Schema):
    key = fields.String()
    value = fields.String()

# Mock models
class DummyDomain:
    def __init__(self, name):
        self.name = name
    def to_dict(self):
        return {"domain": self.name, "mode": "direct", "alias": None, "sub_link_only": False}
    def to_schema(self):
        return DomainSchema().load(self.to_dict())

class DummyProxy:
    def __init__(self, name):
        self.name = name
    def to_dict(self):
        return {"name": self.name, "enable": True, "proto": "vless"}
    def to_schema(self):
        return ProxySchema().load(self.to_dict())

class DummyConfig:
    def __init__(self, k, v):
        self.k = k
        self.v = v
    def to_dict(self):
        return {"key": self.k, "value": str(self.v)}
    def to_schema(self):
        return HConfigSchema().load(self.to_dict())

domains = [DummyDomain(f"d{i}") for i in range(100)]
proxies = [DummyProxy(f"p{i}") for i in range(100)]
configs = [DummyConfig(f"k{i}", i) for i in range(100)]

print(f"Items: {len(domains)} domains, {len(proxies)} proxies, {len(configs)} configs")

def test_original():
    res_domains = [d.to_schema() for d in domains]
    res_proxies = [p.to_schema() for p in proxies]
    res_configs = [c.to_schema() for c in configs]
    return res_domains, res_proxies, res_configs

def test_optimized():
    # Load once with marshmallow Schema instances outside the loop
    d_schema = DomainSchema(many=True)
    p_schema = ProxySchema(many=True)
    c_schema = HConfigSchema(many=True)

    res_domains = d_schema.load([d.to_dict() for d in domains])
    res_proxies = p_schema.load([p.to_dict() for p in proxies])
    res_configs = c_schema.load([c.to_dict() for c in configs])
    return res_domains, res_proxies, res_configs

# warmup
test_original()
test_optimized()

start = time.time()
for _ in range(100):
    test_original()
end = time.time()
print(f"Original logic: {end - start:.4f}s")

start = time.time()
for _ in range(100):
    test_optimized()
end = time.time()
print(f"Optimized logic (many=True): {end - start:.4f}s")
