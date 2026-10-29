#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

class HistoryRows {
 public:
  HistoryRows(const char *path, const char *row = nullptr, size_t cap = SIZE_MAX, bool allowMissing = true);
  ~HistoryRows();
  HistoryRows(const HistoryRows &) = delete;
  HistoryRows &operator=(const HistoryRows &) = delete;
  bool next(char *row, size_t size);
  bool ok() const { return valid; }
 private:
  FILE *file = nullptr;
  long end = 0;
  const char *pending = nullptr;
  bool valid = true;
};

bool historyLast(const char *path, char *row, size_t size);
bool historyCopy(const char *src, const char *dst, size_t cap, size_t &written);
bool historySave(const char *path, const char *row, size_t cap);
bool historyAppend(const char *path, const char *row, size_t cap, size_t trim);
