"""Decode production escaping with an independent JSON parser."""
import json
import subprocess
import pytest
from source_test_support import ROOT,compile_cpp

@pytest.fixture(scope='session')
def json_binary(tmp_path_factory):
    source='#include <string>\n#include <cstdio>\nusing String=std::string;\n'
    source+=(ROOT/'include/json_string.h').read_text().replace('#pragma once','').replace('#include <Arduino.h>','')
    source+='int main(int argc,char **argv) { if(argc!=2) return 1; printf("%s",jstr(argv[1]).c_str()); }'
    return compile_cpp(tmp_path_factory.mktemp('json'),source)

@pytest.mark.parametrize('value',[
    '', 'Kitchen\nMeter', 'tab\treturn\rback\bform\f', 'quote"backslash\\',
    ''.join(chr(c) for c in range(1,32)), 'Zähler Süd ☀️', '<meter>&value',
])
def test_json_roundtrip(json_binary,value):
    encoded=subprocess.check_output([str(json_binary),value],text=True)
    assert json.loads(encoded)==value
    assert all(ord(c)>=32 for c in encoded)
