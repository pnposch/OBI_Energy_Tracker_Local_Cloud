"""Compile production JSON, HTTP CSV, and FTP exporters."""
import csv
import io
import json
import subprocess
import pytest
from source_test_support import ROOT, compile_cpp, function

@pytest.fixture(scope='session')
def exports_binary(tmp_path_factory):
    source = r'''
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <string>
#include <algorithm>
#include <ctime>
#include <cstdint>
class String : public std::string {
 public:
  using std::string::string;
  String(const std::string &s) : std::string(s) {}
  int indexOf(char c) const { auto p=find(c); return p==npos ? -1 : (int)p; }
  String substring(int a,int b) const { return substr(a,b-a); }
  void trim() { auto a=find_first_not_of(" \r\n\t"); if(a==npos) clear(); else *this=substr(a,find_last_not_of(" \r\n\t")-a+1); }
};
std::string output;
struct Server { void sendContent(const String &s) { assert(s.size()<2000); output+=s; } } server;
struct WiFiClient { bool fail=false; size_t print(const String &s) { if(fail) return 0; output+=s; return s.size(); } };
static const char *dailyHeader="date,day_start_epoch,import_wh,export_wh,day_wh,night_wh,ht_wh,st_wh,nt_wh\n";
static const char *rawHeader="date,epoch,import_wh,export_wh,power_w\n";
static uint32_t g_ftpWinStart=0,g_ftpWinEnd=UINT32_MAX;
String fpS(const String &s) { return s; }
String fpD(const String &s) { return s; }
void currentDaily(const String &,char *row,size_t size) { snprintf(row,size,"2000000000,1,2,3,4,5,6,7\n"); }
'''
    source += (ROOT/'include/history_io.h').read_text().replace('#pragma once','')
    source += (ROOT/'src/history_io.cpp').read_text().replace('#include "history_io.h"','')
    web=(ROOT/'src/gateway_web.cpp').read_text()
    for name in ['static void streamRows(', 'static String isoLocal(', 'static bool writeHistoryCsv(', 'static void sendCsvRows(']:
        source += '\n'+function(web,name)
    source += r'''
int main(int argc,char **argv) {
  assert(argc==3); setenv("TZ","UTC",1); tzset();
  HistoryRows rows(argv[2]);
  if(!strcmp(argv[1],"json")) streamRows(rows);
  else if(!strcmp(argv[1],"csv")) sendCsvRows(rows,rawHeader);
  else {
    WiFiClient client; client.fail=!strcmp(argv[1],"ftp_fail");
    if(!strcmp(argv[1],"ftp_window")) { g_ftpWinStart=1800000010; g_ftpWinEnd=1800000020; }
    bool ok=writeHistoryCsv(client,argv[2],true);
    if(client.fail) { assert(!ok); return 0; }
    assert(ok);
  }
  fwrite(output.data(),1,output.size(),stdout);
}
'''
    return compile_cpp(tmp_path_factory.mktemp('exports'),source)

@pytest.fixture
def history(tmp_path):
    path=tmp_path/'daily'
    path.write_text(''.join(f'{1800000000+i},123,45,,-850\n' for i in range(4000)))
    assert path.stat().st_size>65535
    return path

def output(binary,mode,path):
    return subprocess.check_output([str(binary),mode,str(path)],text=True)

def test_json_complete(exports_binary,history):
    rows=json.loads('['+output(exports_binary,'json',history)+']')
    assert len(rows)==4000 and rows[-1]==[1800003999,123,45,None,-850]

def test_http_csv_complete(exports_binary,history):
    rows=list(csv.reader(io.StringIO(output(exports_binary,'csv',history))))
    assert len(rows)==4001 and rows[-1][1:]==['1800003999','123','45','','-850']

def test_ftp_complete(exports_binary,history):
    rows=list(csv.reader(io.StringIO(output(exports_binary,'ftp',history))))
    assert len(rows)==4002 and rows[-1][1:]==['2000000000','1','2','3','4','5','6','7']

def test_ftp_window(exports_binary,history):
    rows=list(csv.reader(io.StringIO(output(exports_binary,'ftp_window',history))))
    assert [int(r[1]) for r in rows[1:]]==list(range(1800000010,1800000020))

def test_ftp_short_write(exports_binary,history):
    output(exports_binary,'ftp_fail',history)
