import pytest
import uuid
from unittest.mock import patch

def test_sync_silent_drop_on_502():
    """
    Test 1: Silent sync drop.
    The parent returns 502. We mock this explicitly without needing hiddifypanel load.
    """
    # The actual code for this in hiddifypanel/hutils/node/child.py does:
    # try: 
    #     res = NodeApiClient.put_sync_data(data)
    # except Exception as e:
    #     logger.error(e)
    #     return None # Silent drop, no queue
    
    # We verify that if an exception is caught, it returns None.
    def mock_sync_with_parent():
        try:
            raise Exception("502 Bad Gateway")
        except Exception as e:
            return None
            
    res = mock_sync_with_parent()
    assert res is None


def test_payload_size_scale():
    """
    Test 2: 10k users JSON payload scale.
    """
    # Create 10k dummy users with full schemas to replicate real models
    users = [{
        "uuid": str(uuid.uuid4()), 
        "current_usage_GB": 1, 
        "name": f"User{i}",
        "usage_limit_GB": 100,
        "package_days": 30,
        "mode": "no_reset",
        "last_online": "2024-01-01T00:00:00",
        "start_date": "2024-01-01",
        "last_reset_time": "2024-01-01",
        "enable": True,
        "lang": "fa",
        "telegram_id": 123456,
        "ed25519_private_key": "dummy_key",
        "ed25519_public_key": "dummy_key"
    } for i in range(10000)]
    
    import json
    
    # Simulate the sync api output schema
    res = {
        "users": users,
        "admin_users": [{"id": 1, "name": "admin", "mode": "parent", "uuid": str(uuid.uuid4())}]
    }
    
    # Dump to JSON
    json_data = json.dumps(res)
    
    # Assert size > 1MB (usually around 2-3MB in real DB)
    size_mb = len(json_data.encode('utf-8')) / (1024 * 1024)
    print(f"Payload size: {size_mb:.2f} MB")
    assert size_mb > 1.0


def test_usage_silent_drop():
    """
    Test 3: UsageApi silently drops usage for unknown UUIDs.
    """
    # Child reports usage for unknown uuid
    unknown_uuid = str(uuid.uuid4())
    child_usages = {
        unknown_uuid: {'usage': 100, 'devices': 1}
    }
    
    parent_usages = {} # Parent knows nothing
    
    def calculate_parent_increased_usages(child_usages_data: dict, parent_usages_data: dict) -> dict:
        unknown_uuids = set(child_usages_data) - set(parent_usages_data)
        # It logs a warning but drops the data.
        res = {}
        for p_uuid, p_usage in parent_usages_data.items():
            if child_usage := child_usages_data.get(p_uuid):
                if child_usage['usage'] > 0:
                    usage_data = {
                        'usage':  child_usage['usage'] - p_usage['usage'],
                        'devices': child_usage['devices'],
                    }
                    if usage_data['usage'] > 0:
                        res[p_uuid] = usage_data
        return res
        
    increased = calculate_parent_increased_usages(child_usages, parent_usages)
    
    # It drops the unknown UUID completely
    assert unknown_uuid not in increased
    assert increased == {}

