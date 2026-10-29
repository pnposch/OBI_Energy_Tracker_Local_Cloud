#pragma once
#include <Arduino.h>

static inline String jstr(const char *s) {
  static const char hex[] = "0123456789abcdef";
  String out = "\"";
  for (; *s; ++s) {
    unsigned char c = (unsigned char)*s;
    if (c < 0x20) {
      out += "\\u00";
      out += hex[c >> 4]; out += hex[c & 15];
    } else {
      if (c == '\"' || c == '\\') out += '\\';
      out += (char)c;
    }
  }
  return out + "\"";
}
