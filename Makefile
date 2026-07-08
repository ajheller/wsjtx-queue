PYTHON ?= python3
SBITX_HOST ?= pi@sbitx.local
SBITX_DIR ?= ~/wsjtx-queue
SBITX_TARGET ?= $(SBITX_HOST):$(SBITX_DIR)

.PHONY: test format format-check demo hub-demo deploy-sbitx

test:
	$(PYTHON) -m unittest discover -s tests

format:
	black wsjtx_queue.py wsjtx_udp_hub.py tests

format-check:
	black --check wsjtx_queue.py wsjtx_udp_hub.py tests

demo:
	$(PYTHON) wsjtx_queue.py --call AK6IM --demo --view both

hub-demo:
	$(PYTHON) wsjtx_udp_hub.py \
		--listen 127.0.0.1:2237 \
		--client gridtracker=127.0.0.1:2238:control \
		--client queue=127.0.0.1:2240:readonly

deploy-sbitx:
	ssh $(SBITX_HOST) "mkdir -p $(SBITX_DIR)"
	scp -r wsjtx_queue.py wsjtx_udp_hub.py wanted $(SBITX_TARGET)/
