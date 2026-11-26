CFLAGS = -std=c11 -Wall -Wextra -Werror -O1 -g -I../main
run: test_logic
	./test_logic
test_logic: test_logic.c ../main/level.c ../main/rate.c ../main/policy.c ../main/fdclevel.c ../main/tilt.c
	$(CC) $(CFLAGS) -o $@ $^ -lm
clean:
	rm -f test_logic scenarios_bin
scenarios: scenarios_bin
	./scenarios_bin
scenarios_bin: scenarios.c ../main/level.c ../main/rate.c ../main/policy.c ../main/fdclevel.c ../main/tilt.c
	$(CC) $(CFLAGS) -o $@ $^ -lm
.PHONY: run clean scenarios
