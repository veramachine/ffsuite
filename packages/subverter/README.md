# subverter

Subtitle and transcript readers into one model: SubRip, WebVTT, LRC, CSV and
TSV, and whisper-cli's and WhisperX's JSON.

A file read becomes what it holds: its cues, the word timings where the format
keeps them, notes on what it held that the model does not, and a refusal --
with its reason -- for what cannot be read.

| Format  | Read as                                                                                                        |
| ------- | -------------------------------------------------------------------------------------------------------------- |
| SubRip  | cues; WhisperX's highlighted cues read back into words                                                         |
| WebVTT  | cues, as SubRip's; `has_references`: its texts hold HTML character references, each run between tags `decoded` |
| LRC     | a line's time, its text                                                                                        |
| CSV/TSV | start, end, text (milliseconds), columns by header, as whisper-cli and WhisperX write them                     |
| JSON    | whisper-cli's and WhisperX's: chunks and word timings                                                          |

## Installing

```sh
pip install subverter
```

Python 3.13 or later; the standard library alone.

## Using it

```pycon
>>> import subverter
>>> reading = subverter.read("srt", b"1\n00:00:01,000 --> 00:00:02,500\nHello <i>there</i>\n", "talk.srt")
>>> reading.cues
(Cue(start=1000, end=2500, text='Hello <i>there</i>', segment=''),)
>>> subverter.untagged(reading.cues[0].text)
'Hello there'
>>> subverter.read("json", b"[1, 2]", "talk.json")
Traceback (most recent call last):
  ...
subverter.Error: not a whisper-cli (.transcription) or WhisperX (.segments) JSON transcript: talk.json
```

Times are milliseconds. A text that cannot be read is refused:
`subverter.Error`, its message the reason.

## Licence

Part of [ffsuite](https://github.com/veramachine/ffsuite), beside ffman: its own package.
Licensed under either of
[MIT](https://github.com/veramachine/ffsuite/blob/main/packages/subverter/LICENSE-MIT)
or [Apache-2.0](https://github.com/veramachine/ffsuite/blob/main/packages/subverter/LICENSE-APACHE),
at your option.
