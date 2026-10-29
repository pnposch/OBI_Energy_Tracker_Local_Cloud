"""Compile extracted handlers against focused hardware fakes."""

import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    tokens = r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]'
    for match in re.finditer(tokens, source[brace:], re.S):
        if match[0] == '{':
            depth += 1
        elif match[0] == '}':
            depth -= 1
            if depth == 0:
                return source[start:brace + match.end()]
    raise ValueError(f'Unclosed function: {signature}')


def compile_cpp(directory, source):
    path = directory / 'test.cpp'
    path.write_text(source)
    binary = directory / 'test'
    subprocess.run([os.environ.get('CXX', 'g++'), '-std=c++11', '-Wall', '-Wextra',
                    '-Werror', '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error',
                    str(path), '-o', str(binary)], check=True)
    return binary
