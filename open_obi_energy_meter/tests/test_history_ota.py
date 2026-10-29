"""Snapshot failures must prevent overwriting history."""
import subprocess
import pytest
from source_test_support import ROOT,compile_cpp,function

@pytest.mark.parametrize('mounted,success',[(0,0),(1,0),(1,1)])
def test_snapshot_gate(tmp_path,mounted,success):
    source='''
#include <cassert>
bool g_paused=false,g_bulkMounted=false,success=false;
int snapshots=0,unmounts=0;
bool snapshotBulkIntoTail() { ++snapshots; return success; }
void unmountBulk() { ++unmounts; }
void unmountTail() { ++unmounts; }
struct Logger { void println(const char *) {} } Serial;
'''+function((ROOT/'src/ota_hist.cpp').read_text(),'bool otaHist_prepareForFlash()')+f'''
int main() {{
  g_bulkMounted={mounted}; success={success};
  bool ok=otaHist_prepareForFlash();
  assert(ok==(!g_bulkMounted || success));
  assert(g_paused==ok && unmounts==(ok ? 2 : 0));
  assert(snapshots=={mounted});
}}
'''
    subprocess.run([str(compile_cpp(tmp_path,source))],check=True)
