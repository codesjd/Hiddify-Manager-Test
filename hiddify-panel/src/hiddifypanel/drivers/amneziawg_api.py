import json
import os
import threading

from .abstract_driver import DriverABS
from hiddifypanel.models import User, hconfig, ConfigEnum
from hiddifypanel.panel.run_commander import Command, commander
import redis


# Deliberately a different redis key than wireguard_api.py's "wg:users-usage"
# even though both drivers key off the same User.wg_pub column (AmneziaWG
# reuses the WireGuard per-user keypair columns) - the two interfaces
# (hiddifywg vs hiddifyawg) measure completely independent traffic, so
# sharing one cache would corrupt both drivers' delta calculations whenever
# a user has both enabled at once.
USERS_USAGE = "awg:users-usage"


class AmneziaWgApi(DriverABS):
    def get_redis_client(self):
        if not hasattr(self, 'redis_client'):
            with self._init_lock:
                if not hasattr(self, 'redis_client'):
                    self.redis_client = redis.from_url(os.environ.get("REDIS_URI_SSH",""))

        return self.redis_client

    def is_enabled(self) -> bool:
        return hconfig(ConfigEnum.amneziawg_client_enable)

    def __init__(self) -> None:
        super().__init__()
        self.pub_uuid_map={}
        self._init_lock = threading.Lock()
        self._map_lock = threading.Lock()

    def __load_pubkey_uuid_map(self):
        from hiddifypanel.database import db
        users = db.session.query(User).all()
        self.pub_uuid_map={u.wg_pub: u.uuid for u in users}

    def __convert_pub_key_to_uuid(self,pubkeys):
        res={}
        can_reload_map=True
        for key in pubkeys:
            if uuid:=self.pub_uuid_map.get(key):
                res[key]=uuid
            elif can_reload_map:
                with self._map_lock:
                    self.__load_pubkey_uuid_map()
                can_reload_map=False
                if uuid:=self.pub_uuid_map.get(key):
                    res[key]=uuid
        return res

    def __get_awg_usages(self) -> dict:
        raw_output = commander(Command.update_awg_usage, run_in_background=False)
        data = {}
        for line in raw_output.split('\n'):
            if not line:
                continue
            sections = line.split()
            if len(sections) < 3:
                continue
            data[sections[0]] = {
                'down': int(sections[1]),
                'up': int(sections[2]),
            }

        return data

    def __get_local_usage(self) -> dict:
        usage_data = self.get_redis_client().get(USERS_USAGE)
        if usage_data:
            return json.loads(usage_data)

        return {}

    def __sync_local_usages(self) -> dict:
        local_usage = self.__get_local_usage()
        awg_usage = self.__get_awg_usages()

        res = {}
        # remove local usage that is removed from awg usage
        for local_wg_pub in local_usage.copy().keys():
            if local_wg_pub not in awg_usage:
                del local_usage[local_wg_pub]

        uuid_map = self.__convert_pub_key_to_uuid(awg_usage.keys())
        for wg_pub, usage_stats in awg_usage.items():
            uuid = uuid_map.get(wg_pub)

            if not local_usage.get(wg_pub):
                local_usage[wg_pub] = {"uuid": uuid, "usage": usage_stats}
                continue
            res[uuid] = self.calculate_reset(local_usage[wg_pub]['usage'], usage_stats)
            local_usage[wg_pub] = {"uuid": uuid, "usage": usage_stats}

        self.get_redis_client().set(USERS_USAGE, json.dumps(local_usage))

        return res

    def calculate_reset(self, last_usage: dict, current_usage: dict) -> dict:
        res = {
            'up': current_usage['up'] - last_usage['up'],
            'down': current_usage['down'] - last_usage['down'],
        }

        if res['up'] < 0:
            res['up'] = 0
        if res['down'] < 0:
            res['down'] = 0
        return res

    def get_enabled_users(self):
        if not hconfig(ConfigEnum.amneziawg_client_enable):
            return {}
        usages = self.__get_awg_usages()
        new_wg_pubs = set(usages.keys())
        old_usages = self.__get_local_usage()
        old_wg_pubs = set(old_usages.keys())
        enabled = {u['uuid']: 1 for u in old_usages.values()}
        not_included = new_wg_pubs - old_wg_pubs
        if not_included:
            users = User.query.filter(User.wg_pub.in_(not_included)).all()
            for u in users:
                enabled[u.uuid] = 1

        return enabled

    def add_client(self, user):
        pass

    def remove_client(self, user):
        pass

    def get_all_usage(self, reset=True):
        if not hconfig(ConfigEnum.amneziawg_client_enable):
            return {}
        all_usages = self.__sync_local_usages()
        res = {}
        for uuid,use in all_usages.items():
            res[uuid] = use['up'] + use['down']
        return res
