import time
import uuid

class User:
    def __init__(self, wg_pub, u):
        self.wg_pub = wg_pub
        self.uuid = u

class Query:
    def __init__(self, users):
        self.users = users
    def filter(self, condition):
        # mock filter
        pubs = condition
        filtered = [u for u in self.users if u.wg_pub in pubs]
        return Query(filtered)
    def all(self):
        return self.users

class UserModel:
    def __init__(self, users):
        self.query = Query(users)
        self.wg_pub = "wg_pub"

users = [User(f"pub_{i}", f"uuid_{i}") for i in range(1000)]
User = UserModel(users)

class InClause:
    def __init__(self, values):
        self.values = values

User.wg_pub = type("wg_pub_col", (), {"in_": lambda self, values: values})()

not_included = {f"pub_{i}" for i in range(500)}

def original_code():
    enabled = {}
    users_list = User.query.filter(User.wg_pub.in_(not_included)).all()
    for u in users_list:
        enabled[u.uuid] = 1
    return enabled

def optimized_code():
    # What's the best way to optimize?
    # If not_included is a set of pubkeys, and we query the DB for users matching these pubkeys,
    # the inefficiency is querying the DB inside a loop, but it's not a loop, it's just one query.
    # Wait, the issue says: "This code block filters a small number of users. Might be better to cache user objects or batch check if not_included is larger."
    # Wait, the original code in `get_enabled_users`:
    # not_included = new_wg_pubs - old_wg_pubs
    # if not_included:
    #     users = User.query.filter(User.wg_pub.in_(not_included)).all()
    #     for u in users:
    #         enabled[u.uuid] = 1
    #
    pass
