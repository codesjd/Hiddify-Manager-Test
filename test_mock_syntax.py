import sys
import os

# Append the src directory to path
sys.path.append(os.path.join(os.getcwd(), 'hiddify-panel', 'src'))

import importlib
import ast

def check_syntax(filepath):
    with open(filepath, 'r') as f:
        source = f.read()
    try:
        ast.parse(source)
        print("Syntax is OK.")
    except SyntaxError as e:
        print(f"Syntax error: {e}")

check_syntax("hiddify-panel/src/hiddifypanel/hutils/node/child.py")
