# squeeze virtual test bench: the real firmware compiled twice (parent, child) against ESP-IDF shims.
#   make                     -> ./sim         (firmware in ../main)
#   make before              -> ./sim_before  (firmware as committed in git HEAD, for before/after runs)
#   python3 experiments.py   (see sim/README.md)
CC ?= cc
CFLAGS = -std=gnu11 -O1 -g -Wall -Wextra -Wno-unused-parameter -D_GNU_SOURCE
FWDIR ?= ../main
TAG ?= cur
SIM ?= sim
CHILD ?= 0xFF8000
SLEEP ?= 2000
DEEP ?= 4000
SRC = main grip shaper turn proto bmp280 bmp280_comp hw radio
FW = $(addprefix $(FWDIR)/,$(addsuffix .c,$(SRC))) shim.c

$(SIM): world.c ../main/bmp280_comp.c build/$(TAG)/unitA.o build/$(TAG)/unitB.o
	$(CC) $(CFLAGS) -o $@ world.c ../main/bmp280_comp.c build/$(TAG)/unitA.o build/$(TAG)/unitB.o -lpthread -lm

build/$(TAG)/unit%.o: $(FW) world.h $(wildcard shim/*.h shim/*/*.h) sdkconfig.in.h Makefile
	@mkdir -p build/$(TAG)/$*/obj
	@role=$$( [ "$*" = A ] && echo PARENT || echo CHILD ); swell=$$( [ "$*" = A ] && echo 90 || echo 65 ); \
	 sed "s/@ROLE@/$$role/; s/@SWELL@/$$swell/; s/@CHILD@/$(CHILD)/; s/@SLEEP@/$(SLEEP)/; s/@DEEP@/$(DEEP)/" sdkconfig.in.h > build/$(TAG)/$*/sdkconfig.h
	@for f in $(FW); do $(CC) $(CFLAGS) -Ibuild/$(TAG)/$* -Ishim -I. -I$(FWDIR) -c $$f -o build/$(TAG)/$*/obj/$$(basename $$f .c).o || exit 1; done
	@ld -r -o build/$(TAG)/$*/raw.o build/$(TAG)/$*/obj/*.o
	@nm -u build/$(TAG)/$*/raw.o | awk '{print "u$*_" $$2 " " $$2}' > build/$(TAG)/$*/undef.map
	@objcopy --prefix-symbols=u$*_ build/$(TAG)/$*/raw.o build/$(TAG)/$*/pref.o
	@objcopy --redefine-syms=build/$(TAG)/$*/undef.map build/$(TAG)/$*/pref.o $@
	@echo "unit $* ($(TAG)): firmware compiled and linked"

before:
	@mkdir -p build/before_src
	@for f in $(SRC) board bmp280 bmp280_comp grip hw proto radio shaper turn; do \
	   git show HEAD:squeeze/firmware/main/$$f.c > build/before_src/$$f.c 2>/dev/null || true; \
	   git show HEAD:squeeze/firmware/main/$$f.h > build/before_src/$$f.h 2>/dev/null || true; done
	@find build/before_src -size 0 -delete
	@sed -i 's|#include "bmp280.h"|#include "bmp280.h"\n#include <stdbool.h>  /* sim: the one compile fix */|' build/before_src/bmp280.c
	$(MAKE) FWDIR=build/before_src TAG=before SIM=sim_before CHILD=0xFF5A00
.PHONY: before
