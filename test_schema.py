import sys
import os

# Append the src directory to path
sys.path.append(os.path.join(os.getcwd(), 'hiddify-panel', 'src'))

from hiddifypanel.panel.commercial.restapi.v2.parent.schema import DomainSchema, ProxySchema, HConfigSchema

print("DomainSchema instance:", DomainSchema())
print("ProxySchema instance:", ProxySchema())
print("HConfigSchema instance:", HConfigSchema())
