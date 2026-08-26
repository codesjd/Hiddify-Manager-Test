import re

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "r") as f:
    content = f.read()

new_content = re.sub(
    r"""        user_link = request\.url_root\.replace\('http://', 'https://'\)\.rstrip\('/'\) \+ f"/{proxy_path}/client/"
        if not g\.user_agent\['is_browser'\]:
            return redirect\(user_link\)

        return render_template\('redirect_to_user\.html', user_link=user_link\)""",
    """        if not g.user_agent['is_browser']:
            return redirect(f"/{proxy_path}/client/")

        user_link = request.url_root.replace('http://', 'https://').rstrip('/') + f"/{proxy_path}/client/"
        return render_template('redirect_to_user.html', user_link=user_link)""",
    content
)

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "w") as f:
    f.write(new_content)
