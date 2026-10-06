"""The formats' examples, each its skill's own (test_skills holds them to it): read, written, compared."""

CUE = """REM GENRE "Alternative Rock"
REM DATE 1991
PERFORMER "My Band"
TITLE "The Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Opening"
    PERFORMER "My Band"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "The Road"
    INDEX 00 04:15:00
    INDEX 01 04:17:52
  TRACK 03 AUDIO
    TITLE "Arrival"
    INDEX 01 09:02:74
"""

FFMETADATA = r""";FFMETADATA1
title=bike\\shed
;this line is a comment
artist=FFmpeg troll team
x_custom=a\=b
artist-sort=troll team, FFmpeg
[STREAM]
language=eng
[CHAPTER]
TIMEBASE=1/1000
START=0
END=60000
title=chapter \#1
[CHAPTER]
TIMEBASE=1/1000
START=60000
END=120000
title=two\
lines
"""

VORBIS = r"""TITLE=The Long Way
ARTIST=Ana Souza
ARTIST=Rui Lima
DATE=2026-10-03
TRACKNUMBER=1
TRACKTOTAL=12
DESCRIPTION=Unabridged\nread by the authors
CHAPTER000=00:00:00.000
CHAPTER000NAME=Departure
CHAPTER001=00:12:30.000
CHAPTER001NAME=The Road
CHAPTER002=00:41:05.500
CHAPTER002NAME=Arrival
"""
