import time
import random
import string

class MockUserQuery:
    def __init__(self, data):
        self.data = data
        self.wg_pub = "mock"

    def filter(self, in_clause):
        # simulate DB latency
        time.sleep(0.005) # 5ms
        return self

    def all(self):
        return self.data

    def in_(self, items):
        pass

class MockUser:
    def __init__(self, wg_pub, uuid):
        self.wg_pub = wg_pub
        self.uuid = uuid

# Generate mock data
users_data = [MockUser('pub' + str(i), 'uuid' + str(i)) for i in range(100)]
pub_uuid_map = {u.wg_pub: u.uuid for u in users_data}

class User:
    query = MockUserQuery(users_data)
    wg_pub = MockUserQuery([])

# Old approach
def old_approach(not_included):
    enabled = {}
    users = User.query.filter(User.wg_pub.in_(not_included)).all()
    for u in users:
        enabled[u.uuid] = 1
    return enabled

# New approach
def __convert_pub_key_to_uuid(pubkeys):
    res = {}
    for key in pubkeys:
        if uuid := pub_uuid_map.get(key):
            res[key] = uuid
    return res

def new_approach(not_included):
    enabled = {}
    uuid_map = __convert_pub_key_to_uuid(not_included)
    for uuid in uuid_map.values():
        enabled[uuid] = 1
    return enabled

not_included = {'pub1', 'pub2', 'pub3'}

# Benchmark old
start_time = time.time()
for _ in range(100):
    old_approach(not_included)
old_time = time.time() - start_time

# Benchmark new
start_time = time.time()
for _ in range(100):
    new_approach(not_included)
new_time = time.time() - start_time

print(f"Old approach (simulated DB): {old_time:.4f} seconds")
print(f"New approach (in-memory dict): {new_time:.4f} seconds")
print(f"Speedup: {old_time / new_time:.2f}x")
