import time
from marshmallow import Schema, fields

class DomainSchema(Schema):
    domain = fields.String(required=True)
    alias = fields.String(allow_none=True)
    sub_link_only = fields.Boolean(required=True)
    # just a few fields

# simulating to_schema
class DummyDomain:
    def __init__(self, name):
        self.name = name
    def to_dict(self):
        return {"domain": self.name, "alias": "alias", "sub_link_only": True}

    def to_schema(self):
        return DomainSchema().load(self.to_dict())

domains = [DummyDomain(f"d{i}") for i in range(1000)]

start = time.time()
for _ in range(100):
    res1 = [d.to_schema() for d in domains]
end = time.time()
print(f"Instantiating inside loop: {end - start:.4f}s")

def optimized_to_schema(domains):
    schema = DomainSchema()
    return [schema.load(d.to_dict()) for d in domains]

start = time.time()
for _ in range(100):
    res2 = optimized_to_schema(domains)
end = time.time()
print(f"Instantiating outside loop: {end - start:.4f}s")

# even better: many=True
def even_more_optimized(domains):
    schema = DomainSchema(many=True)
    return schema.load([d.to_dict() for d in domains])

start = time.time()
for _ in range(100):
    res3 = even_more_optimized(domains)
end = time.time()
print(f"many=True: {end - start:.4f}s")
