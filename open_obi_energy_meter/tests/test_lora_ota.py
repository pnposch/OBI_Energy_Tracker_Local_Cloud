"""Run the production cmd-33 dispatch and responder."""
import subprocess
import pytest
from source_test_support import ROOT,compile_cpp,function

@pytest.fixture(scope='session')
def ota_binary(tmp_path_factory):
    main=(ROOT/'src/main.cpp').read_text()
    source=r'''
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <vector>
static uint8_t image[96]={};
static uint8_t *g_ota=image;
static uint32_t g_otaSize=96,g_otaServed=0,g_otaSfHoldMs=0,now=10000;
static uint8_t g_otaVersion=90,g_otaTarget[3]={1,2,3};
static bool g_otaActive=true,g_otaPulled=false;
std::vector<std::vector<uint8_t>> sent;
struct Logger { template<typename...T> void printf(const char *,T...) {} void println(const char *) {} } Serial;
uint32_t millis() { return now; }
uint16_t obi_crc16(const uint8_t *,size_t) { return 0; }
size_t obi_build_frame(uint8_t *out,const uint8_t *,int,const uint8_t *data,size_t size) { memcpy(out,data,size); return size; }
void txFrame(const uint8_t *data,size_t size,const char *) { sent.emplace_back(data,data+size); }
struct Reader { int lastRssi=0,lastSnr=0; uint32_t lastSeenMs=0; bool inBootloader=false; } reader;
Reader *addReader(const uint8_t *) { return &reader; }
'''
    source+=function(main,'static bool otaAccepts(')+'\n'+function(main,'static void serveOtaRequest(')
    dispatch=main[main.index('    case 33: {'):main.index('    case 20: case 21: {')]
    source+='\nvoid request(uint32_t pos,const uint8_t *handle=g_otaTarget,size_t len=11) {\n'
    source+='uint8_t d[11]={0,0,0,0,0,1,0,(uint8_t)(pos>>24),(uint8_t)(pos>>16),(uint8_t)(pos>>8),(uint8_t)pos};\nint rssi=0,snr=0; switch(33) {\n'+dispatch+'}}\n'
    expiry=next(line.strip() for line in main.splitlines() if line.strip().startswith('if (!ota && g_otaPulled &&'))
    source+='void expire() { bool ota=g_otaActive; '+expiry+' }\n'
    source+=r'''
int main(int argc,char **argv) {
  assert(argc==2);
  if(!strcmp(argv[1],"wrap")) now=UINT32_MAX-1000;
  for(size_t i=0;i<sizeof image;++i) image[i]=(uint8_t)i;
  if(!strcmp(argv[1],"short")) { request(0,g_otaTarget,10); assert(sent.empty() && g_otaActive); return 0; }
  request(64);
  assert(sent.size()==1 && !g_otaActive && g_otaServed==96);
  assert(sent[0].size()==72 && !memcmp(sent[0].data()+6,image+64,32));
  for(size_t i=38;i<70;i++) assert(sent[0][i]==0);
  uint32_t deadline=g_otaSfHoldMs;
  if(!strcmp(argv[1],"other_reader")) {
    uint8_t other[3]={9,9,9}; request(64,other); assert(sent.size()==1); return 0;
  }
  if(!strcmp(argv[1],"cancel")) { g_ota=nullptr; g_otaPulled=false; request(64); assert(sent.size()==1); return 0; }
  if(!strcmp(argv[1],"new_upload")) { g_otaPulled=false; request(64); assert(sent.size()==1); return 0; }
  now+=1000; request(64);
  assert(sent.size()==2 && sent[0]==sent[1] && g_otaSfHoldMs==deadline);
  request(UINT32_MAX); assert(sent.size()==3 && sent.back().size()==13);
  now+=1999; request(0); assert(sent.size()==4 && !memcmp(sent.back().data()+6,image,64));
  ++now; request(64); assert(sent.size()==4);
  assert(!g_otaActive && g_otaSfHoldMs==deadline);
  expire(); assert(!g_otaPulled);
  now+=UINT32_MAX/2+2; request(64); assert(sent.size()==4);
}
'''
    return compile_cpp(tmp_path_factory.mktemp('lora-ota'),source)

@pytest.mark.parametrize('scenario',['retry','wrap','short','other_reader','cancel','new_upload'])
def test_retry_window(ota_binary,scenario):
    subprocess.run([str(ota_binary),scenario],check=True)
