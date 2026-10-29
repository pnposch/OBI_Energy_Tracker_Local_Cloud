"""Exercise the production upload cancellation handler."""

import subprocess

import pytest

from source_test_support import ROOT, compile_cpp, function


@pytest.fixture(scope='session')
def upload_handler(tmp_path_factory):
    source = r'''
#include <cassert>
#include <cstddef>
#include <cstring>
enum { UPLOAD_FILE_START, UPLOAD_FILE_WRITE, UPLOAD_FILE_END, UPLOAD_FILE_ABORTED };
struct Filename { const char *c_str() { return "firmware.bin"; } };
struct HTTPUpload { int status=0; Filename filename; unsigned char *buf=nullptr; size_t currentSize=16, totalSize=16; };
struct Server { HTTPUpload data; HTTPUpload &upload() { return data; } } server;
struct Logger { template<typename...T> void printf(const char *,T...) {} } Serial;
bool paused=false, authorized=true, failSnapshot=false;
unsigned resumes=0;
bool otaHist_prepareForFlash() { paused=!failSnapshot; return !failSnapshot; }
void otaHist_abortFlash() { paused=false; ++resumes; }
bool authValid() { return authorized; }
const size_t UPDATE_SIZE_UNKNOWN=~size_t{0};
struct Updater {
  bool active=false, failBegin=false, failWrite=false, failEnd=false;
  unsigned aborts=0;
  bool begin(size_t) { if(active || failBegin) return false; active=true; return true; }
  size_t write(unsigned char *,size_t size) { if(failWrite) { active=false; return 0; } return size; }
  bool end(bool) { active=false; return !failEnd; }
  void abort() { active=false; ++aborts; }
  void printError(Logger &) {}
} Update;
static bool s_selfOtaOk=false;
'''
    source += function((ROOT / 'src/gateway_web.cpp').read_text(), 'static void handleSelfOtaUpload()')
    source += r'''
void event(int status) { server.data.status=status; handleSelfOtaUpload(); }
int main(int argc,char **argv) {
  assert(argc==2);
  if(!strcmp(argv[1],"unauthorized")) {
    authorized=false; event(UPLOAD_FILE_START); event(UPLOAD_FILE_ABORTED);
    assert(!paused && !Update.active && !s_selfOtaOk && Update.aborts==0 && resumes==0);
  } else if(!strcmp(argv[1],"foreign_update")) {
    Update.active=true;
    event(UPLOAD_FILE_ABORTED);
    assert(Update.active && Update.aborts==0 && resumes==0);
  } else if(!strcmp(argv[1],"abort_retry")) {
    event(UPLOAD_FILE_START); event(UPLOAD_FILE_WRITE); event(UPLOAD_FILE_ABORTED);
    assert(!paused && !Update.active && !s_selfOtaOk && Update.aborts==1 && resumes==1);
    event(UPLOAD_FILE_ABORTED);
    assert(Update.aborts==1 && resumes==1);
    event(UPLOAD_FILE_START); event(UPLOAD_FILE_WRITE); event(UPLOAD_FILE_END);
    assert(s_selfOtaOk && !Update.active && paused);
  } else if(!strcmp(argv[1],"snapshot_failure")) {
    failSnapshot=true; event(UPLOAD_FILE_START); event(UPLOAD_FILE_WRITE); event(UPLOAD_FILE_END);
    assert(!paused && !Update.active && !s_selfOtaOk && resumes==0);
  } else if(!strcmp(argv[1],"success")) {
    event(UPLOAD_FILE_START); event(UPLOAD_FILE_WRITE); event(UPLOAD_FILE_END);
    assert(s_selfOtaOk && !Update.active && paused && Update.aborts==0 && resumes==0);
  } else {
    Update.failBegin=!strcmp(argv[1],"begin_failure");
    Update.failWrite=!strcmp(argv[1],"write_failure");
    Update.failEnd=!strcmp(argv[1],"end_failure");
    assert(Update.failBegin || Update.failWrite || Update.failEnd);
    event(UPLOAD_FILE_START); event(UPLOAD_FILE_WRITE); event(UPLOAD_FILE_END);
    event(UPLOAD_FILE_ABORTED);
    assert(!s_selfOtaOk && !Update.active && !paused && resumes==1);
  }
}
'''
    return compile_cpp(tmp_path_factory.mktemp('self-ota'), source)


@pytest.mark.parametrize('scenario', [
    'abort_retry', 'success', 'unauthorized', 'foreign_update',
    'begin_failure', 'write_failure', 'end_failure', 'snapshot_failure',
])
def test_upload_lifecycle(upload_handler, scenario):
    subprocess.run([str(upload_handler), scenario], check=True)
