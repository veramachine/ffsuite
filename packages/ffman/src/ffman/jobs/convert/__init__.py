"""``ffman convert``: one job, in the order its bash command ran (stage A).

The imperative shell of a job: it probes, asks phase 2's pure decisions in the
bash command's order (resize resolved its output early, before sizing), builds
one ffmpeg command, and writes through a partial file.

One module a flow (``resize``, ``burn``, ``attach``, ``youtube``), chosen by
``dispatch``; what they share: the effects' ``passes``, the ``render``, the
``output``. ``options`` validates the command line's answer.
"""
