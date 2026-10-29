# History streaming

History persistence, recovery, HTTP exports and FTP exports use bounded rows instead of whole-file Arduino Strings. Daily files larger than 64 KiB remain readable. Daily responses merge the current RAM row without changing the stored file. FTP applies its existing time window while streaming.

New daily rows append directly while within the file cap. Replacement and compaction write a temporary file before renaming it over the original. Read, write, flush, close and rename failures preserve the original file and are logged. File caps stay unchanged. Replacement needs sufficient free filesystem space for the retained rows; a full filesystem can reject a replacement, so this is not a new disk-full recovery mechanism. Raw and daily appends use normal append semantics.

OTA snapshots use the same bounded reader and reserve one eighth of the tail partition for filesystem overhead. Snapshot failures cancel browser and GitHub firmware updates before `Update.begin()`. Other boards continue updating without the OTA history backend.

Host regressions cover files above 64 KiB, same-day replacement, retention boundaries, last-row recovery, malformed input, injected storage failures, complete HTTP/FTP exports, export windows, short network writes and the OTA snapshot gate. Real LittleFS failure and OTA tests on OBI hardware remain necessary.
