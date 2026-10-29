#include "history_io.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>

static bool fileEnd(FILE *f, long &end) {
  if (fseek(f, 0, SEEK_END)) return false;
  end = ftell(f);
  return end >= 0;
}

static bool lastStart(FILE *f, long end, long &start) {
  char buf[128];
  bool trailing = true;
  while (end > 0) {
    long pos = end > (long)sizeof buf ? end - sizeof buf : 0;
    size_t n = (size_t)(end - pos);
    if (fseek(f, pos, SEEK_SET) || fread(buf, 1, n, f) != n) return false;
    for (size_t i = n; i > 0; --i) {
      char c = buf[i - 1];
      if (trailing && (c == '\n' || c == '\r')) continue;
      trailing = false;
      if (c == '\n') { start = pos + (long)i; return true; }
    }
    end = pos;
  }
  start = 0;
  return true;
}

HistoryRows::HistoryRows(const char *path, const char *row, size_t cap, bool allowMissing) : pending(row) {
  file = fopen(path, "rb");
  if (!file && (!allowMissing || errno != ENOENT)) { valid = false; return; }
  if (file && !fileEnd(file, end)) { valid = false; return; }
  if (file && row && end) {
    long start;
    char last[128];
    if (!lastStart(file, end, start) || fseek(file, start, SEEK_SET) ||
        !fgets(last, sizeof last, file)) { valid = false; return; }
    if (strtoul(last, nullptr, 10) == strtoul(row, nullptr, 10)) end = start;
  }
  size_t extra = row ? strlen(row) : 0;
  if (file && row && end) {
    if (fseek(file, end - 1, SEEK_SET)) { valid = false; return; }
    int c = fgetc(file);
    if (c == EOF) { valid = false; return; }
    if (c != '\n') ++extra;
  }
  if (extra > cap) { valid = false; return; }
  long cut = (size_t)end > cap - extra ? end - (long)(cap - extra) : 0;
  if (file) {
    if (fseek(file, cut ? cut - 1 : 0, SEEK_SET)) { valid = false; return; }
    if (cut) {
      int c;
      do { c = fgetc(file); } while (c != '\n' && c != EOF && ftell(file) < end);
      if (ferror(file)) valid = false;
    }
  }
}

HistoryRows::~HistoryRows() { if (file) fclose(file); }

bool HistoryRows::next(char *row, size_t size) {
  if (!valid || size < 2) return false;
  if (file && ftell(file) < end) {
    size_t n = 0;
    while (ftell(file) < end) {
      int c = fgetc(file);
      if (c == EOF) { valid = false; return false; }
      if (n + 1 >= size) { valid = false; return false; }
      row[n++] = (char)c;
      if (c == '\n') break;
    }
    if (pending && n && row[n - 1] != '\n') {
      if (n + 1 >= size) { valid = false; return false; }
      row[n++] = '\n';
    }
    row[n] = 0;
    return true;
  }
  if (!pending) return false;
  size_t n = strlen(pending);
  if (n >= size) { valid = false; return false; }
  memcpy(row, pending, n + 1);
  pending = nullptr;
  return true;
}

bool historyLast(const char *path, char *row, size_t size) {
  FILE *f = fopen(path, "rb");
  if (!f) return false;
  long end, start;
  bool ok = fileEnd(f, end) && end && lastStart(f, end, start) &&
            !fseek(f, start, SEEK_SET) && fgets(row, size, f);
  if (ok && !strchr(row, '\n') && !feof(f)) ok = false;
  fclose(f);
  return ok;
}

static bool writeRows(HistoryRows &rows, const char *dst, size_t &written) {
  written = 0;
  char temp[128];
  if (snprintf(temp, sizeof temp, "%s.tmp", dst) >= (int)sizeof temp || !rows.ok()) return false;
  FILE *f = fopen(temp, "wb");
  if (!f) return false;
  char row[128];
  bool ok = true;
  while (rows.next(row, sizeof row)) {
    size_t n = strlen(row);
    if (fwrite(row, 1, n, f) != n) { ok = false; break; }
    written += n;

  }
  ok = ok && rows.ok();
  if (fflush(f)) ok = false;
  if (fclose(f)) ok = false;
  if (ok && rename(temp, dst)) ok = false;
  if (!ok) { remove(temp); written = 0; }
  return ok;
}

bool historyCopy(const char *src, const char *dst, size_t cap, size_t &written) {
  HistoryRows rows(src, nullptr, cap, false);
  return writeRows(rows, dst, written);
}

bool historySave(const char *path, const char *row, size_t cap) {
  size_t length = strlen(row);
  if (length > cap) return false;
  FILE *f = fopen(path, "rb");
  if (f) {
    long end, start;
    char last[128];
    bool ok = fileEnd(f, end);
    bool append = false;
    if (ok && end && (size_t)end <= cap - length) {
      ok = lastStart(f, end, start) && !fseek(f, start, SEEK_SET) &&
           fgets(last, sizeof last, f);
      append = ok && strchr(last, '\n') &&
               strtoul(last, nullptr, 10) != strtoul(row, nullptr, 10);
    }
    if (fclose(f)) ok = false;
    if (!ok) return false;
    if (append) return historyAppend(path, row, cap, cap);
  } else if (errno != ENOENT) return false;
  HistoryRows rows(path, row, cap);
  size_t written;
  return writeRows(rows, path, written);
}

bool historyAppend(const char *path, const char *row, size_t cap, size_t trim) {
  FILE *f = fopen(path, "ab");
  if (!f) return false;
  size_t n = strlen(row);
  bool ok = fwrite(row, 1, n, f) == n;
  if (fflush(f)) ok = false;
  long size = ftell(f);
  if (size < 0) ok = false;
  if (fclose(f)) ok = false;
  if (!ok || (size_t)size <= cap) return ok;
  size_t written;
  return historyCopy(path, path, trim, written);
}
