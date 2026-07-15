PYTHON ?= python3
SBITX_HOST ?= pi@sbitx.local
SBITX_DIR ?= ~/wsjtx-queue
SBITX_TARGET ?= $(SBITX_HOST):$(SBITX_DIR)
TEXTUAL_VENV ?= .venv-textual
TEXTUAL_PYTHON := $(TEXTUAL_VENV)/bin/python
TEXTUAL_ENV := PYTHONPATH=

.PHONY: test format format-check demo textual-venv textual-demo textual-run hub-demo replay-alltxt-demo deploy-sbitx

test:
	$(PYTHON) -m unittest discover -s tests

format:
	black wsjtx_queue.py wsjtx_udp_hub.py wsjtx_queue_textual.py wsjtx_udp_record.py wsjtx_udp_replay.py tests

format-check:
	black --check wsjtx_queue.py wsjtx_udp_hub.py wsjtx_queue_textual.py wsjtx_udp_record.py wsjtx_udp_replay.py tests

demo:
	$(PYTHON) wsjtx_queue.py --call AK6IM --demo --view both

textual-venv:
	$(PYTHON) -m venv $(TEXTUAL_VENV)
	$(TEXTUAL_ENV) $(TEXTUAL_PYTHON) -m pip install --upgrade pip
	$(TEXTUAL_ENV) $(TEXTUAL_PYTHON) -m pip install --upgrade --force-reinstall "platformdirs>=4,<5" "typing-extensions>=4.4,<5"
	$(TEXTUAL_ENV) $(TEXTUAL_PYTHON) -m pip install -r requirements-textual.txt

textual-demo: textual-venv
	$(TEXTUAL_ENV) $(TEXTUAL_PYTHON) wsjtx_queue_textual.py --call AK6IM --grid CM87um --demo

textual-run: textual-venv
	$(TEXTUAL_ENV) $(TEXTUAL_PYTHON) wsjtx_queue_textual.py

hub-demo:
	$(PYTHON) wsjtx_udp_hub.py \
		--listen 127.0.0.1:2237 \
		--client gridtracker=127.0.0.1:2238:control \
		--client queue=127.0.0.1:2240:readonly

replay-alltxt-demo:
	$(PYTHON) wsjtx_udp_replay.py --alltxt --dry-run sample-data/alltxt-excerpt.txt

deploy-sbitx:
	ssh $(SBITX_HOST) "mkdir -p $(SBITX_DIR)"
	scp -r Makefile wsjtx_queue.py wsjtx_udp_hub.py wsjtx_queue_textual.py wsjtx_udp_record.py wsjtx_udp_replay.py requirements-textual.txt sample-data wanted $(SBITX_TARGET)/
