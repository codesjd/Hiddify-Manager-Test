class MyClass:
    def __init__(self):
        self.pub_uuid_map = {"pub1": "uuid1"}

    def __convert_pub_key_to_uuid(self, pubkeys):
        return {key: self.pub_uuid_map.get(key) for key in pubkeys if key in self.pub_uuid_map}

    def get_enabled_users(self, not_included):
        enabled = {}
        uuid_map = self.__convert_pub_key_to_uuid(not_included)
        for uuid in uuid_map.values():
            enabled[uuid] = 1
        return enabled

m = MyClass()
print(m.get_enabled_users(["pub1"]))
