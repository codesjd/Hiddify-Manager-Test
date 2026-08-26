import re

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "r") as f:
    content = f.read()

new_content = re.sub(
    r"""        if not g\.user_agent\['is_browser'\]:
            return redirect\(f"/{proxy_path}/client/"\)""",
    """        if not g.user_agent['is_browser']:
            return redirect(f"/{proxy_path}/client/")""",
    content
)

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "w") as f:
    f.write(new_content)
