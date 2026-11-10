# Convenience targets for the lab. Run `make help` to list them.
COMPOSE := docker compose
S ?=

.PHONY: help up down logs reset verify

help:
	@echo "make up | down | logs [S=service] | reset | verify"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100 $(S)

reset:
	$(COMPOSE) down -v --remove-orphans
	find detection/suricata/logs detection/zeek/logs -mindepth 1 ! -name .gitkeep -delete

verify:
	$(COMPOSE) ps
	$(COMPOSE) exec -T attacker python - < tools/verify_lab.py
