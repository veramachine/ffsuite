/* Everything libcue parsed from a cue sheet, through its public API (libcue.h): the disc's
 * CD-Text and REMs, each track's file, mode, ISRC, start and length (frames, 1/75 s), pre- and
 * postgap, indexes 00-02, flags (PRE DCP 4CH SCMS), CD-Text and REMs. libcue exports no getter
 * for CATALOG, so none is printed.
 *
 * Build against libcue 2.3.0 (nixpkgs' pin; its parser needs bison and flex):
 *   cmake -S libcue-2.3.0 -B build -DBUILD_SHARED_LIBS=OFF && make -C build
 *   cc -I libcue-2.3.0 -I build -o cuedump cuedump.c build/libcue.a
 * Usage: cuedump FILE.cue */
#include <stdio.h>
#include "libcue.h"

static const char *s(const char *v) { return v ? v : "-"; }

static void cdtext(Cdtext *c, const char *who) {
	static const struct { enum Pti p; const char *n; } f[] = {
		{PTI_TITLE, "TITLE"}, {PTI_PERFORMER, "PERFORMER"}, {PTI_SONGWRITER, "SONGWRITER"},
		{PTI_COMPOSER, "COMPOSER"}, {PTI_ARRANGER, "ARRANGER"}, {PTI_MESSAGE, "MESSAGE"},
		{PTI_DISC_ID, "DISC_ID"}, {PTI_GENRE, "GENRE"}, {PTI_UPC_ISRC, "UPC_ISRC"}};
	for (unsigned i = 0; i < sizeof f / sizeof *f; i++)
		if (cdtext_get(f[i].p, c)) printf("  %s cdtext %s=[%s]\n", who, f[i].n, cdtext_get(f[i].p, c));
}

static void rems(Rem *r, const char *who) {
	static const struct { enum RemType t; const char *n; } f[] = {
		{REM_DATE, "DATE"}, {REM_REPLAYGAIN_ALBUM_GAIN, "REPLAYGAIN_ALBUM_GAIN"},
		{REM_REPLAYGAIN_ALBUM_PEAK, "REPLAYGAIN_ALBUM_PEAK"},
		{REM_REPLAYGAIN_TRACK_GAIN, "REPLAYGAIN_TRACK_GAIN"},
		{REM_REPLAYGAIN_TRACK_PEAK, "REPLAYGAIN_TRACK_PEAK"}};
	for (unsigned i = 0; i < sizeof f / sizeof *f; i++)
		if (rem_get(f[i].t, r)) printf("  %s rem %s=[%s]\n", who, f[i].n, rem_get(f[i].t, r));
}

int main(int argc, char **argv) {
	FILE *in = fopen(argv[1], "r");
	Cd *cd = in ? cue_parse_file(in) : NULL;
	if (!cd) { printf("  parse failed\n"); return 1; }
	printf("  disc cdtextfile=[%s] tracks=%d\n", s(cd_get_cdtextfile(cd)), cd_get_ntrack(cd));
	cdtext(cd_get_cdtext(cd), "disc");
	rems(cd_get_rem(cd), "disc");
	for (int i = 1; i <= cd_get_ntrack(cd); i++) {
		Track *t = cd_get_track(cd, i);
		char who[16];
		snprintf(who, sizeof who, "track %d", i);
		printf("  %s file=[%s] mode=%d isrc=[%s] start=%ld length=%ld pre=%ld post=%ld idx00=%ld idx01=%ld idx02=%ld flags=%d%d%d%d\n",
		       who, s(track_get_filename(t)), track_get_mode(t), s(track_get_isrc(t)), track_get_start(t),
		       track_get_length(t), track_get_zero_pre(t), track_get_zero_post(t), track_get_index(t, 0),
		       track_get_index(t, 1), track_get_index(t, 2), track_is_set_flag(t, FLAG_PRE_EMPHASIS),
		       track_is_set_flag(t, FLAG_COPY_PERMITTED), track_is_set_flag(t, FLAG_FOUR_CHANNEL),
		       track_is_set_flag(t, FLAG_SCMS));
		cdtext(track_get_cdtext(t), who);
		rems(track_get_rem(t), who);
	}
	return 0;
}
