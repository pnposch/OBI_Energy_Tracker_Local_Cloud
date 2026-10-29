"""Large history files and storage failure regression tests."""
import subprocess
import pytest
from source_test_support import ROOT, compile_cpp

@pytest.fixture(scope='session')
def history_binary(tmp_path_factory):
    source = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cassert>
#include <string>
static const char *fault = "";
static size_t put(const void *p, size_t a, size_t b, FILE *f) {
  if (!strcmp(fault,"write")) return 0;
  return fwrite(p,a,b,f);
}
static int get(FILE *f) { return !strcmp(fault,"read") ? EOF : fgetc(f); }
static int flush(FILE *f) { int r=fflush(f); return !strcmp(fault,"flush") ? EOF : r; }
static int closeFile(FILE *f) { int r=fclose(f); return !strcmp(fault,"close") ? EOF : r; }
static int moveFile(const char *a,const char *b) {
  return !strcmp(fault,"rename") ? -1 : rename(a,b);
}
#define fgetc get
#define fwrite put
#define fflush flush
#define fclose closeFile
#define rename moveFile
''' + (ROOT / 'src/history_io.cpp').read_text().replace('#include "history_io.h"', (ROOT / 'include/history_io.h').read_text().replace('#pragma once','')) + r'''
#undef fgetc
#undef fwrite
#undef fflush
#undef fclose
#undef rename
int main(int argc,char **argv) {
  assert(argc>=4);
  std::string cmd=argv[1];
  fault=argc>5 ? argv[5] : "";
  size_t cap=argc>4 ? strtoul(argv[4],nullptr,10) : SIZE_MAX;
  bool ok=false;
  if(cmd=="copy") { size_t n; ok=historyCopy(argv[2],argv[3],cap,n); }
  if(cmd=="save") ok=historySave(argv[2],argv[3],cap);
  if(cmd=="append") ok=historyAppend(argv[2],argv[3],cap,cap/2);
  if(cmd=="last") { char row[128]; ok=historyLast(argv[2],row,sizeof row); if(ok) fputs(row,stdout); }
  if(cmd=="rows") {
    HistoryRows rows(argv[2],strlen(argv[3]) ? argv[3] : nullptr,cap);
    char row[128]; while(rows.next(row,sizeof row)) fputs(row,stdout);
    ok=rows.ok();
  }
  return ok ? 0 : 1;
}
'''
    return compile_cpp(tmp_path_factory.mktemp('history'), source)

@pytest.fixture
def records():
    return [f'{1800000000+i*86400},1234567,123456,1,2,3,4,5\n' for i in range(2400)]

def run(binary, mode, path, value='', cap=2**31, fault=''):
    return subprocess.run([str(binary), mode, str(path), str(value), str(cap), fault], capture_output=True, text=True)

def test_large_copy(history_binary, tmp_path, records):
    src=tmp_path/'source'; dst=tmp_path/'target'
    content=''.join(records); assert len(content)>84000
    src.write_text(content)
    assert run(history_binary,'copy',src,dst).returncode==0
    assert dst.read_text()==content
    assert run(history_binary,'last',dst).stdout==records[-1]

def test_daily_upsert(history_binary,tmp_path,records):
    path=tmp_path/'daily'; path.write_text(''.join(records))
    row=records[-1].split(',')[0]+',9,8,7,6,5,4,3\n'
    assert run(history_binary,'save',path,row,114688).returncode==0
    assert path.read_text()==''.join(records[:-1])+row
    new='1999999999,1,2,3,4,5,6,7\n'
    assert run(history_binary,'save',path,new,114688).returncode==0
    assert path.read_text()==''.join(records[:-1])+row+new

def test_virtual_row(history_binary,tmp_path,records):
    path=tmp_path/'daily'; content=''.join(records); path.write_text(content)
    row=records[-1].split(',')[0]+',9,8,7,6,5,4,3\n'
    result=run(history_binary,'rows',path,row)
    assert result.returncode==0 and result.stdout==''.join(records[:-1])+row
    assert path.read_text()==content

@pytest.mark.parametrize('cap',[0,1,41,42,100,4096,65535])
def test_bounded_tail(history_binary,tmp_path,records,cap):
    src=tmp_path/'source'; dst=tmp_path/'target'; src.write_text(''.join(records))
    assert run(history_binary,'copy',src,dst,cap).returncode==0
    result=dst.read_text()
    assert len(result)<=cap and ''.join(records).endswith(result)
    assert not result or result.splitlines()[0] in [r.rstrip() for r in records]

@pytest.mark.parametrize('fault',['read','write','flush','close','rename'])
def test_failed_replace_preserves_file(history_binary,tmp_path,records,fault):
    path=tmp_path/'daily'; content=''.join(records); path.write_text(content)
    replacement=records[-1].split(',')[0]+',1,2\n'
    result=run(history_binary,'save',path,replacement,114688,fault)
    assert result.returncode==1
    assert path.read_text()==content
    assert not (tmp_path/'daily.tmp').exists()

def test_missing_source_preserves_target(history_binary,tmp_path):
    dst=tmp_path/'target'; dst.write_text('retained\n')
    assert run(history_binary,'copy',tmp_path/'missing',dst).returncode==1
    assert dst.read_text()=='retained\n'

def test_malformed_row_preserves_target(history_binary,tmp_path):
    src=tmp_path/'source'; dst=tmp_path/'target'
    src.write_text('x'*150+'\n'); dst.write_text('retained\n')
    assert run(history_binary,'copy',src,dst).returncode==1
    assert dst.read_text()=='retained\n'

def test_append_trim(history_binary,tmp_path,records):
    path=tmp_path/'raw'; path.write_text(''.join(records))
    row='1999999999,12,34,-850\n'
    assert run(history_binary,'append',path,row,40000).returncode==0
    result=path.read_text()
    assert len(result)<=20000 and result.endswith(row)
    assert (''.join(records)+row).endswith(result)

def test_new_file(history_binary,tmp_path):
    path=tmp_path/'new'; row='1999999999,12,34\n'
    assert run(history_binary,'save',path,row,100).returncode==0
    assert path.read_text()==row

def test_unterminated_file(history_binary,tmp_path):
    src=tmp_path/'source'; dst=tmp_path/'target'
    src.write_text('1800000000,1,2')
    assert run(history_binary,'copy',src,dst,14).returncode==0
    assert dst.read_text()==src.read_text()
    assert run(history_binary,'save',src,'1800000001,3,4\n',100).returncode==0
    assert src.read_text()=='1800000000,1,2\n1800000001,3,4\n'

def test_daily_append_avoids_copy(history_binary,tmp_path,records):
    path=tmp_path/'daily'; content=''.join(records); path.write_text(content)
    row='2100000000,1,2,3,4,5,6,7\n'
    (tmp_path/'daily.tmp').mkdir()
    assert run(history_binary,'save',path,row,114688).returncode==0
    assert path.read_text()==content+row
