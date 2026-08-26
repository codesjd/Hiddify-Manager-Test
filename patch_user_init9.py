import re

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "r") as f:
    content = f.read()

new_content = re.sub(
    r"""    @app\.route\('/<proxy_path>/<user_secret>'\)
    @app\.route\('/<proxy_path>/<user_secret>/'\)
    @app\.doc\(hide=True\)
    def backward_compatibality\(proxy_path, user_secret\):
        from flask import request, redirect, render_template, g

        if not g\.user_agent\.get\('is_browser', False\):
            return redirect\(f"/{proxy_path}/client/"\)

        user_link = request\.url_root\.replace\('http://', 'https://'\)\.rstrip\('/'\) \+ f"/{proxy_path}/client/"
        return render_template\('redirect_to_user\.html', user_link=user_link\)""",
    """    @app.route('/<proxy_path>/<uuid:user_secret>')
    @app.route('/<proxy_path>/<uuid:user_secret>/')
    @app.doc(hide=True)
    def backward_compatibality(proxy_path, user_secret):
        from flask import request, redirect, render_template, g

        if not g.user_agent.get('is_browser', False):
            return redirect(f"/{proxy_path}/client/")

        user_link = request.url_root.replace('http://', 'https://').rstrip('/') + f"/{proxy_path}/client/"
        return render_template('redirect_to_user.html', user_link=user_link)""",
    content
)

with open("hiddify-panel/src/hiddifypanel/panel/user/__init__.py", "w") as f:
    f.write(new_content)
