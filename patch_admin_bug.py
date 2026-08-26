with open("hiddify-panel/src/hiddifypanel/models/admin.py", "r") as f:
    code = f.read()

code = code.replace(
"""        if dbuser.id != 1:
            parent = u.parent_admin_uuid if _dto else data.get('parent_admin_uuid')
            if parent == (u.uuid if _dto else data.get('uuid')) or not parent:
                parent_admin = cls.current_admin_or_owner()""",
"""        if dbuser.id != 1:
            parent = u.parent_admin_uuid if _dto else data.get('parent_admin_uuid')
            # Fix parens logic around the uuid assignment
            u_uuid = u.uuid if _dto else data.get('uuid')
            if parent == u_uuid or not parent:
                parent_admin = cls.current_admin_or_owner()""")

with open("hiddify-panel/src/hiddifypanel/models/admin.py", "w") as f:
    f.write(code)
