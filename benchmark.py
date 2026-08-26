import time
import os
import sys

# Adding src to path
sys.path.append(os.path.join(os.getcwd(), 'hiddify-panel/src'))

from hiddifypanel.drivers.amneziawg_api import AmneziaWgApi
from hiddifypanel.drivers.wireguard_api import WireguardApi

print("Benchmark script ready.")
