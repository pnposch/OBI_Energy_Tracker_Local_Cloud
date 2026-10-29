"""Compare production calendar boundaries with zoneinfo."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import os
import subprocess
import pytest
from source_test_support import ROOT,compile_cpp,function

@pytest.fixture(scope='session')
def calendar_binary(tmp_path_factory):
    source='''
#include <ctime>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cassert>
static time_t now;
static int g_ftpWindow;
bool timeValid() { return true; }
time_t fakeTime(time_t *) { return now; }
#define time fakeTime
'''
    web=(ROOT/'src/gateway_web.cpp').read_text()
    source+=function(web,'static uint32_t localDayStart(')+'\n'+function(web,'static void ftpWindowBounds(')
    source+='''
int main(int argc,char **argv) {
  assert(argc==3); tzset();
  now=strtoll(argv[1],nullptr,10); g_ftpWindow=atoi(argv[2]);
  uint32_t start,end; ftpWindowBounds(start,end);
  printf("%u %u %u",localDayStart(now),start,end);
}
'''
    return compile_cpp(tmp_path_factory.mktemp('calendar'),source)

@pytest.mark.parametrize('date',[
    '2026-03-29T01:00:00','2026-03-29T12:00:00','2026-03-30T12:00:00',
    '2026-10-25T01:00:00','2026-10-25T12:00:00','2026-10-26T12:00:00',
    '2027-01-01T12:00:00','2028-03-01T12:00:00',
])
def test_calendar_window(calendar_binary,date):
    zone=ZoneInfo('Europe/Berlin'); now=datetime.fromisoformat(date).replace(tzinfo=zone)
    today=now.replace(hour=0,minute=0,second=0)
    previous=today-timedelta(days=1)
    env=dict(os.environ,TZ='CET-1CEST,M3.5.0,M10.5.0/3')
    result=subprocess.check_output([str(calendar_binary),str(int(now.timestamp())),'2'],env=env,text=True)
    assert list(map(int,result.split()))==[int(today.timestamp()),int(previous.timestamp()),int(today.timestamp())]

@pytest.mark.parametrize('window,seconds',[(1,86400),(3,7*86400),(4,30*86400)])
def test_rolling_window(calendar_binary,window,seconds):
    now=int(datetime(2026,3,30,12,tzinfo=ZoneInfo('Europe/Berlin')).timestamp())
    result=subprocess.check_output([str(calendar_binary),str(now),str(window)],env=dict(os.environ,TZ='CET-1CEST,M3.5.0,M10.5.0/3'),text=True)
    _,start,end=map(int,result.split())
    assert start==now-seconds and end==2**32-1
