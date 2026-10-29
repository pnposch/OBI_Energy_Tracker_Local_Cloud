#pragma once
#include "FreeRTOS.h"
struct FakeSemaphore { bool held = false; };
using SemaphoreHandle_t = FakeSemaphore *;
extern bool testMutexFail;
inline SemaphoreHandle_t xSemaphoreCreateMutex() {
  static FakeSemaphore mutex;
  return testMutexFail ? nullptr : &mutex;
}
inline BaseType_t xSemaphoreTake(SemaphoreHandle_t mutex, TickType_t) {
  assert(!mutex->held);
  mutex->held = true;
  return pdTRUE;
}
inline void xSemaphoreGive(SemaphoreHandle_t mutex) {
  assert(mutex->held);
  mutex->held = false;
}
