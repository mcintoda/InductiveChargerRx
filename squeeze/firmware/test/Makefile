CFLAGS = -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -O1 -g -I../main
SRC = ../main/grip.c ../main/shaper.c ../main/turn.c ../main/proto.c
run: test_logic
	./test_logic
test_logic: test_logic.c $(SRC)
	$(CC) $(CFLAGS) -o $@ $^ -lm
clean:
	rm -f test_logic
.PHONY: run clean
