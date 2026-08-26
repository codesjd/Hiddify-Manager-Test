# Simplified benchmark script without requiring full app context setup
import time

class DummyDomain:
    def __init__(self, name):
        self.name = name
    def to_schema(self):
        # simulate DB load + schema serialization
        # time.sleep(0.0001)
        return {"domain": self.name}

class DummyProxy:
    def __init__(self, name):
        self.name = name
    def to_schema(self):
        # time.sleep(0.0001)
        return {"proxy": self.name}

class DummyStrConfig:
    def __init__(self, val):
        self.val = val
    def to_schema(self):
        return {"val": self.val}

class DummyBoolConfig:
    def __init__(self, val):
        self.val = val
    def to_schema(self):
        return {"val": self.val}

domains = [DummyDomain(f"d{i}") for i in range(100)]
proxies = [DummyProxy(f"p{i}") for i in range(100)]
str_configs = [DummyStrConfig(f"s{i}") for i in range(50)]
bool_configs = [DummyBoolConfig(i%2==0) for i in range(50)]

class SyncInputSchema:
    pass

class SyncFields:
    domains = 'domains'
    proxies = 'proxies'
    hconfigs = 'hconfigs'

class ModelQuery:
    def __init__(self, items):
        self.items = items
    def all(self):
        return self.items

class Domain:
    query = ModelQuery(domains)
class Proxy:
    query = ModelQuery(proxies)
class StrConfig:
    query = ModelQuery(str_configs)
class BoolConfig:
    query = ModelQuery(bool_configs)

def __get_sync_data_for_api_original(*fields):
    sync_data = SyncInputSchema()
    if len(fields) == 0:
        sync_data.domains = [domain.to_schema() for domain in Domain.query.all()]
        sync_data.proxies = [proxy.to_schema() for proxy in Proxy.query.all()]
        sync_data.hconfigs = [*[u.to_schema() for u in StrConfig.query.all()], *[u.to_schema() for u in BoolConfig.query.all()]]
    else:
        for f in fields:
            match f:
                case SyncFields.domains:
                    sync_data.domains = [domain.to_schema() for domain in Domain.query.all()]
                case SyncFields.proxies:
                    sync_data.proxies = [proxy.to_schema() for proxy in Proxy.query.all()]
                case SyncFields.hconfigs:
                    sync_data.hconfigs = [*[u.to_schema() for u in StrConfig.query.all()], *[u.to_schema() for u in BoolConfig.query.all()]]
    return sync_data

start = time.time()
for _ in range(1000):
    __get_sync_data_for_api_original()
end = time.time()
print(f"Original: {end - start:.4f}s")

def __get_sync_data_for_api_optimized(*fields):
    sync_data = SyncInputSchema()

    def process_domains():
        return [domain.to_schema() for domain in Domain.query.all()]

    def process_proxies():
        return [proxy.to_schema() for proxy in Proxy.query.all()]

    def process_configs():
        return [*[u.to_schema() for u in StrConfig.query.all()], *[u.to_schema() for u in BoolConfig.query.all()]]

    if len(fields) == 0:
        sync_data.domains = process_domains()
        sync_data.proxies = process_proxies()
        sync_data.hconfigs = process_configs()
    else:
        for f in fields:
            match f:
                case SyncFields.domains:
                    sync_data.domains = process_domains()
                case SyncFields.proxies:
                    sync_data.proxies = process_proxies()
                case SyncFields.hconfigs:
                    sync_data.hconfigs = process_configs()
    return sync_data

start = time.time()
for _ in range(1000):
    __get_sync_data_for_api_optimized()
end = time.time()
print(f"Optimized: {end - start:.4f}s")
