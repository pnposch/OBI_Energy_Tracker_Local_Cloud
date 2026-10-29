#pragma once
#include "FreeRTOS.h"
using TaskHandle_t = void *;
using TaskFunction_t = void (*)(void *);
extern TaskFunction_t testWorker;
extern bool testTaskFail;
extern unsigned testTaskCreates;
inline BaseType_t xTaskCreate(TaskFunction_t fn, const char *, unsigned, void *, unsigned, TaskHandle_t *handle) {
  ++testTaskCreates;
  if (testTaskFail) return 0;
  testWorker = fn;
  *handle = reinterpret_cast<TaskHandle_t>(1);
  return pdPASS;
}
struct WorkerYield {};
inline void vTaskDelay(TickType_t delay) { assert(delay == 100); throw WorkerYield{}; }
inline void workerTick() {
  assert(testWorker);
  try { testWorker(nullptr); } catch (WorkerYield &) {}
}
