with open("hiddify-panel/src/tests/test_configs_api.py", "r") as f:
    code = f.read()

if "import os" not in code:
    code = "import os\n" + code

with open("hiddify-panel/src/tests/test_configs_api.py", "w") as f:
    f.write(code)
