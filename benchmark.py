import time
from marshmallow import Schema, fields

class TestSchema(Schema):
    field1 = fields.String()
    field2 = fields.Integer()
    field3 = fields.Boolean()

data = [{"field1": "test", "field2": i, "field3": i % 2 == 0} for i in range(1000)]

start = time.time()
res1 = []
for d in data:
    res1.append(TestSchema().load(d))
end1 = time.time()
print(f"Schema() per item: {end1 - start:.4f}s")

start = time.time()
schema = TestSchema()
res2 = []
for d in data:
    res2.append(schema.load(d))
end2 = time.time()
print(f"Schema() once, .load() per item: {end2 - start:.4f}s")

start = time.time()
schema_many = TestSchema(many=True)
res3 = schema_many.load(data)
end3 = time.time()
print(f"Schema(many=True).load(): {end3 - start:.4f}s")
