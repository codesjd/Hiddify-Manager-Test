import sys
import os

# Append the src directory to path
sys.path.append(os.path.join(os.getcwd(), 'hiddify-panel', 'src'))

from hiddifypanel import create_app
from hiddifypanel.models import DomainType
app = create_app()

with app.app_context():
    from hiddifypanel.panel.commercial.restapi.v2.parent.schema import DomainSchema
    schema = DomainSchema()
    loaded = schema.load({"domain": "x", "sub_link_only": True, "grpc": False, "mode": "direct"})
    print("Type of loaded:", type(loaded))
    print("Loaded content:", loaded)
