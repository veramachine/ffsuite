"""Transcripts that break the rules on purpose: each one aimed at a reader's or a normaliser's edge.

Stage A proved them equal to bash's (its bash comparison); tests/test_ingest.py
checks what must hold of any transcript, on each.
"""

from typing import Final

HOSTILE: Final = {
    # a line too long for one line, in scripts without spaces: Japanese by kinsoku, Thai by
    # its syllables (6.5): never a line opening on 、 or 。, never after เ -- each a text the
    # code before broke there (の|、, ます|。, และเ|รา)
    "long-ja.srt": "1\n00:00:01,000 --> 00:00:04,000\n日本語の文章は単語の間にスペースを入れないの、ですから一行がとても長くなることがあります。「本当ですか？」と彼は言った。\n",
    "long-th.srt": "1\n00:00:01,000 --> 00:00:04,000\nวันนี้เมื่อวานนี้ฝนตกหนักมากจนน้ำท่วมถนนและเราต้องเดินทางกลับบ้านด้วยความลำบากมากที่สุด\n",
    # half a millisecond: through a float 504 and 4024 ms, exactly 505 and 4025 --
    # a centisecond apart in the burned ASS
    "half-ms.srt": "1\n00:00:00,5045 --> 00:00:04,0245\nhalf\n",
    "crlf.csv": 'start,end,text\r\n0,1000,"Hello, ""you"""\r\n1000,2000,Two\r\n',
    "bom.srt": "\ufeff1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n2\n00:00:00,500 --> 00:00:01,500\nEarlier\n",
    "unsorted.lrc": "[00:05.00]Later\n[00:01.50]Sooner\n[00:03]Mid\n",
    "settings.vtt": "WEBVTT\n\nNOTE a note\n\n00:01.000 --> 00:02.500 align:start position:10%\n<b>Bold</b> {\\an8}and \\N more\n\n",
    "hours.srt": "1\n100:00:00,000 --> 100:00:01,000\nLate\n",
    "reversed.srt": "1\n00:00:02,000 --> 00:00:01,000\nBackwards\n\n2\n00:00:03,000 --> 00:00:04,000\n   \n",
    "reordered.csv": 'text,end,start\nhi,2000,1000\n"a,b",4000,3000\n',
    "negative.tsv": "start\tend\ttext\n-500\t800\tneg\nx\t900\tbad start\n",
    "texts.json": '{"segments": [{"start": 0.5, "end": "1.25", "text": "a\\tb\\nc \\\\ d"}, {"start": "x", "end": 2, "text": 7}, {"start": 2, "end": 3, "text": null}, {"start": 3, "end": 4.0004, "text": "four", "words": [{"word": "four", "start": 3.1}, {"word": "tied", "start": 3.1, "end": 3.2}, {"word": "gone"}, "bad", {"word": "late", "start": 9}]}]}',
    "cli.json": '{"transcription": [{"offsets": {"from": 0, "to": 1500}, "text": " hi there"}, {"offsets": {"from": "2000", "to": null}, "text": "no end"}, {"offsets": {"from": 3000, "to": 4000}, "text": ["odd"]}]}',
    "-dash.json": '{"segments": [{"start": 0, "end": 1, "text": "dashed"}]}',
    "neither.json": '{"results": []}',
    "invalid.json": "{nope",
    "notes.txt": "plain text\n",
    "subs.xyz": "x\n",
    "empty.srt": "1\n00:00:01,000 --> 00:00:01,000\nzero\n",
    "halves.json": '{"segments": [{"start": 0.0125, "end": 1.0625, "text": "half", "words": [{"word": "half", "start": 0.0625, "end": 0.1125}]}]}',
    "no-newline.srt": "1\n00:01 --> 00:02\nshort times\n2\n5 --> 7\nbare seconds, no blank line before",
    "blank-lines.srt": "\n\n1\n00:00:01,000 --> 00:00:02,000\nx\n\n\n\n2\n00:00:03,000 --> 00:00:04,000\ny\n",
    "gaps.srt": "1\n00:00:01,000 --> 00:00:02,000\n<u>A</u> b\n\n2\n00:00:02,000 --> 00:00:03,000\nA b\n\n3\n00:00:03,000 --> 00:00:04,000\nA <u>b</u>\n\n",
    "short.tsv": "start\tend\ttext\n100\n\n200\t300\tok\n",
    "types.json": '{"result": {"language": "en"}, "transcription": [{"offsets": {"from": 0, "to": 3000}, "text": " one two", "tokens": [7, {"text": " one", "offsets": {"from": true, "to": {"x": 1}}, "t_dtw": 5}, {"text": " two", "offsets": {"from": 1.5, "to": 2500}, "t_dtw": 12}]}, {"offsets": {"from": 3000, "to": 4000}, "text": " ok", "tokens": [{"text": " ok", "offsets": {"from": 3100, "to": 3900}, "t_dtw": 310}]}, {"offsets": {"from": 4000, "to": 5000}, "text": " none", "tokens": [{"text": " none", "offsets": {"from": 4100, "to": 4900}}]}]}',
    "windows.json": '{"segments": [{"start": 1, "end": 3, "text": "w", "words": "nope"}, {"start": 3, "end": 5, "text": "early late own", "words": [{"word": "early", "start": 2.0, "end": 3.2}, {"word": "own", "start": 3.5, "end": 3.7}, {"word": "tail"}, {"word": "late", "start": 6}]}, {"start": 5, "end": 6, "text": "first", "words": ["x", {"word": "a"}, {"word": "b", "start": 5.5, "end": 5.6}]}]}',
    "empty.lrc": "",
    "emptied.srt": "1\n00:00:01,000 --> 00:00:02,000\n<u>A</u> b\n\n2\n00:00:02,000 --> 00:00:03,000\nA <u>b</u>\n\n3\n00:00:03,000 --> 00:00:04,000\nA b\n\n4\n00:00:04,000 --> 00:00:05,000\n<b></b>\n\n",
    "odd-windows.json": '{"transcription": [{"offsets": {"from": null, "to": "zz"}, "text": " w", "tokens": [{"text": " w", "offsets": {"from": 0, "to": 10}, "t_dtw": 1}]}, {"offsets": {"from": false, "to": 900}, "text": " v", "tokens": [{"text": " v", "offsets": {"from": true, "to": {"k": 1}}, "t_dtw": -2}]}, {"offsets": {"from": 1000, "to": 2000}, "text": " u", "tokens": [{"text": " u", "offsets": {"from": 1000.5, "to": 1999}, "t_dtw": 90}]}]}',
    "anchors.json": '{"segments": [{"start": " 5", "end": 7, "text": "spaced"}, {"start": 8, "end": 9, "text": "a b", "words": [{"word": "a"}, {"word": "  "}, {"word": "b", "start": 8.0, "end": 8.5}]}]}',
    "infinite.json": '{"segments": [{"start": "inf", "end": 1e400, "text": "far"}, {"start": 1, "end": 2, "text": "near", "words": [{"word": "near", "start": {}}]}]}',
    "fractions.json": '{"transcription": [{"offsets": {"from": 1000, "to": 2000}, "text": " u v", "tokens": [{"text": " u", "offsets": {"from": 1000.5, "to": 1499.25}, "t_dtw": 90}, {"text": " v", "offsets": {"from": 1500, "to": 1999}, "t_dtw": 95}]}]}',
    "bounds.json": '{"transcription": [{"offsets": {"from": false, "to": [1]}, "text": " w", "tokens": [{"text": " w", "offsets": {"from": 0, "to": 10}, "t_dtw": 1}]}, {"offsets": {"from": 0, "to": 500}, "text": " x", "tokens": [{"text": " x", "offsets": {"from": 0, "to": 500}}]}]}',
    "spaces.srt": "1\n00:00:01,000 --> 00:00:04,000\nno\xa0break and\u3000ideographic spaces here in one quite long line of text to wrap\n",
}
