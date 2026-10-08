PY ?= python

.PHONY: install voice sandbox bee voice-mode web full test bench eval plan setup secretscan

install:            ## core python deps
	$(PY) -m pip install -r requirements.txt

voice:              ## voice python deps
	$(PY) -m pip install -r requirements-voice.txt

sandbox:            ## build ML sandbox docker image
	docker build -t bee-sandbox:latest ./sandbox

bee:                ## start REPL
	$(PY) -m bee.cli

voice-mode:         ## start voice command mode
	$(PY) -m bee.cli voice

web:                ## start web UI
	$(PY) -m bee.cli web

full:               ## full stack: web + livekit workers + browser + REPL (debt M15)
	$(PY) -m bee.cli full

test:               ## DSA correctness tests
	$(PY) -m pytest tests/ -q

bench:              ## DSA benchmark report
	$(PY) -m bee.dsa.bench

eval:               ## run agent eval suite
	$(PY) -m bee.cli eval

setup:              ## environment check
	$(PY) -m bee.cli setup

secretscan:         ## scan the repo for accidentally-committed secrets
	$(PY) -m bee.security.secretscan
