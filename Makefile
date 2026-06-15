PYTHON ?= python3
SBITX_TARGET ?= pi@sbitx.local:~

.PHONY: test demo hub-demo deploy-sbitx

test:
	$(PYTHON) -m unittest discover -s tests

demo:
	$(PYTHON) wsjtx_queue.py --call AK6IM --demo --view both

hub-demo:
	$(PYTHON) wsjtx_udp_hub.py --listen 127.0.0.1:2237 --client gridtracker=127.0.0.1:2238:readonly --client queue=127.0.0.1:2240:control

deploy-sbitx:
	scp wsjtx_queue.py $(SBITX_TARGET)
