import re
def extract_parent_info_from_url(url):
    pattern = r'^https?://([^/]+)/([^/]+)/([^/]+)/.*$'
    match = re.match(pattern, url)
    if match:
        domain = match.group(1)
        proxy_path = match.group(2)
        admin_uuid = match.group(3)
        return domain, proxy_path, admin_uuid
    else:
        return None, None, None

print(extract_parent_info_from_url("https://example.com/proxy/uuid/admin/"))
