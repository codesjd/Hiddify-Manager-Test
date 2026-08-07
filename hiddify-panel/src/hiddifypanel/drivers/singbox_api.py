import json
import os
from collections import defaultdict

import xtlsapi
from flask import current_app
from loguru import logger

from hiddifypanel.cache import cache
from hiddifypanel.models import *

from .abstract_driver import DriverABS


class SingboxApi(DriverABS):
    def is_enabled(self) -> bool:
        from hiddifypanel.models import hconfig
        from hiddifypanel.models.config_enum import ConfigEnum

        if hconfig(ConfigEnum.core_type) == "singbox":
            return True
        for f in [
            "hysteria_enable",
            "tuic_enable",
            "anytls_enable",
            "shadowsocks2022_enable",
            "naive_enable",
            "mieru_enable",
        ]:
            try:
                if hconfig(ConfigEnum(f)):
                    return True
            except Exception:
                pass
        return False

    def get_singbox_client(self):
        return xtlsapi.SingboxClient("127.0.0.1", 10086)

    def get_enabled_users(self):
        config_dir = os.environ["HIDDIFY_CONFIG_PATH"]
        with open(f"{config_dir}/singbox/configs/01_api.json") as f:
            json_data = json.load(f)
            return {u.split("@")[0]: 1 for u in json_data["experimental"]["v2ray_api"]["stats"]["users"]}

    @cache.cache(ttl=300)
    def get_inbound_tags(self):
        try:
            xray_client = self.get_singbox_client()
            inbounds = [inb.name.split(">>>")[1] for inb in xray_client.stats_query("inbound")]
            # print(f"Success in get inbound tags {inbounds}")
        except Exception as e:
            print(f"error in get inbound tags {e}")
            inbounds = []
        return list(set(inbounds))

    def add_client(self, user):
        pass

    def remove_client(self, user):
        pass

    def get_all_usage(self):
        xray_client = self.get_singbox_client()
        usages = xray_client.stats_query("user", reset=True)

        res = defaultdict(int)
        for use in usages:
            if "user>>>" not in use.name:
                continue
            # print(use.name, use.value)
            uuid = use.name.split(">>>")[1].split("@")[0]
            res[uuid] += use.value  # uplink + downlink
        return res
        # return {u: self.get_usage_imp(u.uuid) for u in users}

    def get_usage_imp(self, uuid):
        xray_client = self.get_singbox_client()
        d = xray_client.get_client_download_traffic(f"{uuid}", reset=True)
        u = xray_client.get_client_upload_traffic(f"{uuid}", reset=True)

        res = None
        if d is None:
            res = u
        elif u is None:
            res = d
        else:
            res = d + u
        if res:
            logger.debug(f"singbox {uuid} d={d} u={u} sum={res}")
        return res
