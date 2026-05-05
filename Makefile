.PHONY: start stop restart status log

LOG_FILE := bot.log
PID_FILE := .pid

start:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "already running (pid=$$(cat $(PID_FILE)))"; \
	else \
		rm -f $(PID_FILE); \
		python3 src/main.py >> $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE); \
		echo "started (pid=$$(cat $(PID_FILE)))"; \
	fi

stop:
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID; sleep 1; \
			if kill -0 $$PID 2>/dev/null; then \
				kill -9 $$PID && echo "force killed (pid=$$PID)"; \
			else \
				echo "stopped (pid=$$PID)"; \
			fi; \
		else \
			echo "not running"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		pkill -9 -f "src/main.py" 2>/dev/null && echo "stopped" || echo "not running"; \
	fi

restart: stop start

status:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "running (pid=$$(cat $(PID_FILE)))"; \
	else \
		echo "not running"; \
	fi

log:
	@tail -n 50 -f $(LOG_FILE)
